package art.lazying.labcanvas.wechatbridge;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** Clears Android's stopped-package state without opening or replacing a display. */
public final class BootstrapReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        context.getSharedPreferences("state", Context.MODE_PRIVATE)
                .edit()
                .putLong("bootstrapped_at_ms", System.currentTimeMillis())
                .apply();
    }
}
