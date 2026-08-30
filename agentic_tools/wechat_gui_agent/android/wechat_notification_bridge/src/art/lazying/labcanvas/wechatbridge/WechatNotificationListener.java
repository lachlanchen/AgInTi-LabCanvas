package art.lazying.labcanvas.wechatbridge;

import android.app.Notification;
import android.os.Bundle;
import android.os.Parcelable;
import android.service.notification.NotificationListenerService;
import android.service.notification.StatusBarNotification;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

/** Captures only WeChat notification text into this app's private sandbox. */
public final class WechatNotificationListener extends NotificationListenerService {
    private static final String WECHAT_PACKAGE = "com.tencent.mm";
    private static final String EVENT_FILE = "events.jsonl";
    private static final int MAX_FIELD_CHARS = 8192;
    private static final long COMPACT_AT_BYTES = 2L * 1024L * 1024L;
    private static final int COMPACT_KEEP_LINES = 1200;
    private static final Object FILE_LOCK = new Object();

    @Override
    public void onListenerConnected() {
        appendLifecycleEvent("listener_connected");
    }

    @Override
    public void onNotificationPosted(StatusBarNotification sbn) {
        if (sbn == null || !WECHAT_PACKAGE.equals(sbn.getPackageName())) {
            return;
        }
        Notification notification = sbn.getNotification();
        if (notification == null) {
            return;
        }
        Bundle extras = notification.extras == null ? new Bundle() : notification.extras;
        try {
            JSONObject event = baseEvent("notification_posted");
            event.put("notification_key", bounded(sbn.getKey()));
            event.put("notification_id", sbn.getId());
            event.put("notification_tag", bounded(sbn.getTag()));
            event.put("post_time_ms", sbn.getPostTime());
            event.put("title", extraText(extras, Notification.EXTRA_TITLE));
            event.put("text", extraText(extras, Notification.EXTRA_TEXT));
            event.put("big_text", extraText(extras, Notification.EXTRA_BIG_TEXT));
            event.put("sub_text", extraText(extras, Notification.EXTRA_SUB_TEXT));
            event.put("summary_text", extraText(extras, Notification.EXTRA_SUMMARY_TEXT));
            event.put("info_text", extraText(extras, Notification.EXTRA_INFO_TEXT));
            event.put("conversation_title", extraText(extras, Notification.EXTRA_CONVERSATION_TITLE));
            event.put("text_lines", textLines(extras));
            event.put("messages", messagingStyleMessages(extras));
            appendEvent(event);
        } catch (JSONException ignored) {
            // A malformed optional notification extra must not stop later events.
        }
    }

    private void appendLifecycleEvent(String kind) {
        try {
            appendEvent(baseEvent(kind));
        } catch (JSONException ignored) {
            // Lifecycle evidence is optional; message capture remains available.
        }
    }

    private JSONObject baseEvent(String kind) throws JSONException {
        long sequence = getSharedPreferences("state", MODE_PRIVATE).getLong("sequence", 0L) + 1L;
        getSharedPreferences("state", MODE_PRIVATE).edit().putLong("sequence", sequence).apply();
        JSONObject event = new JSONObject();
        event.put("schema", "labcanvas-wechat-notification-v1");
        event.put("kind", kind);
        event.put("sequence", sequence);
        event.put("package", WECHAT_PACKAGE);
        event.put("captured_at_ms", System.currentTimeMillis());
        return event;
    }

    private static String extraText(Bundle extras, String key) {
        CharSequence value = extras.getCharSequence(key);
        return bounded(value == null ? "" : value.toString());
    }

    private static JSONArray textLines(Bundle extras) {
        JSONArray output = new JSONArray();
        CharSequence[] lines = extras.getCharSequenceArray(Notification.EXTRA_TEXT_LINES);
        if (lines == null) {
            return output;
        }
        for (CharSequence line : lines) {
            if (line != null && line.length() > 0) {
                output.put(bounded(line.toString()));
            }
        }
        return output;
    }

    private static JSONArray messagingStyleMessages(Bundle extras) {
        JSONArray output = new JSONArray();
        Parcelable[] bundles = extras.getParcelableArray(Notification.EXTRA_MESSAGES);
        if (bundles == null) {
            return output;
        }
        List<Notification.MessagingStyle.Message> messages =
                Notification.MessagingStyle.Message.getMessagesFromBundleArray(bundles);
        for (Notification.MessagingStyle.Message message : messages) {
            try {
                JSONObject item = new JSONObject();
                item.put("text", bounded(String.valueOf(message.getText())));
                item.put("timestamp_ms", message.getTimestamp());
                CharSequence sender = message.getSender();
                item.put("sender", bounded(sender == null ? "" : sender.toString()));
                output.put(item);
            } catch (JSONException ignored) {
                // Keep the other messages from this notification update.
            }
        }
        return output;
    }

    private static String bounded(String value) {
        if (value == null) {
            return "";
        }
        String normalized = value.replace('\u0000', ' ').trim();
        return normalized.length() <= MAX_FIELD_CHARS
                ? normalized
                : normalized.substring(0, MAX_FIELD_CHARS);
    }

    private void appendEvent(JSONObject event) {
        synchronized (FILE_LOCK) {
            File file = new File(getFilesDir(), EVENT_FILE);
            try (FileOutputStream stream = new FileOutputStream(file, true)) {
                stream.write((event.toString() + "\n").getBytes(StandardCharsets.UTF_8));
                stream.flush();
            } catch (Exception ignored) {
                return;
            }
            if (file.length() > COMPACT_AT_BYTES) {
                compact(file);
            }
        }
    }

    private void compact(File file) {
        ArrayList<String> tail = new ArrayList<>();
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(
                new FileInputStream(file), StandardCharsets.UTF_8))) {
            String line;
            while ((line = reader.readLine()) != null) {
                tail.add(line);
                if (tail.size() > COMPACT_KEEP_LINES) {
                    tail.remove(0);
                }
            }
        } catch (Exception ignored) {
            return;
        }
        try (FileOutputStream stream = new FileOutputStream(file, false)) {
            for (String line : tail) {
                stream.write((line + "\n").getBytes(StandardCharsets.UTF_8));
            }
            stream.flush();
        } catch (Exception ignored) {
            // A later event retries normal append; never crash the listener.
        }
    }
}
