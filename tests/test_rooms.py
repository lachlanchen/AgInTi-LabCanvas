from pathlib import Path
import tempfile
import unittest

from agenticapp.rooms import RoomStore, normalize_room_id
from agenticapp.webapp import (
    room_agent_options,
    room_artifact_route,
    room_invites_route,
    room_message_shape,
    room_messages_route,
)


class RoomStoreTests(unittest.TestCase):
    def test_normalize_room_id(self):
        self.assertEqual(normalize_room_id("Lab Agent"), "lab-agent")
        self.assertEqual(normalize_room_id("research_room"), "research_room")
        with self.assertRaises(ValueError):
            normalize_room_id("")

    def test_messages_and_context_stay_room_scoped(self):
        created_payloads = []

        def create_task(payload, storage_dir, *, root, launch):
            created_payloads.append(payload)
            return {"task": {"id": "task-1", "status": "queued"}}

        with tempfile.TemporaryDirectory() as tmp:
            store = RoomStore(tmp, project_root=tmp)
            result = store.post_user_message(
                "labagent",
                "Create a CAD holder",
                sender_id="member-a",
                sender_name="Member A",
                agent_options={"model": "auto", "_room_access_role": "owner"},
                task_creator=create_task,
            )
            store.ensure_room("other-room")

            self.assertEqual(result["task"]["id"], "task-1")
            self.assertEqual(len(store.list_messages("labagent")), 1)
            self.assertEqual(store.list_messages("other-room"), [])
            self.assertEqual(created_payloads[0]["conversation_id"], "room-labagent")
            self.assertEqual(
                created_payloads[0]["context"]["recent_messages"],
                [],
            )
            self.assertEqual(created_payloads[0]["context"]["access_role"], "owner")

    def test_invite_is_room_scoped_and_expiring(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = RoomStore(tmp, project_root=tmp)
            invite = store.create_invite("labagent", label="Test", expires_hours=24)

            self.assertIsNotNone(store.validate_invite("labagent", invite["token"]))
            self.assertIsNone(store.validate_invite("agenttest", invite["token"]))
            self.assertNotIn("token", store.list_invites("labagent")[0])
            self.assertTrue(store.revoke_invite("labagent", invite["id"]))
            self.assertIsNone(store.validate_invite("labagent", invite["token"]))

    def test_completed_task_syncs_once_with_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = Path(tmp)
            store = RoomStore(storage, project_root=storage)
            task_id = "task-complete"

            def create_task(payload, storage_dir, *, root, launch):
                return {"task": {"id": task_id, "status": "queued"}}

            store.post_user_message(
                "labagent",
                "Render it",
                task_creator=create_task,
            )
            task = {
                "id": task_id,
                "status": "completed",
                "reply": "Rendered.",
                "artifacts": [{"path": "agent/tasks/task-complete/artifacts/render.png", "kind": "image"}],
            }

            self.assertEqual(store.sync_tasks("labagent", task_reader=lambda _: task), 1)
            self.assertEqual(store.sync_tasks("labagent", task_reader=lambda _: task), 0)
            messages = store.list_messages("labagent")
            self.assertEqual([item["role"] for item in messages], ["user", "assistant"])
            self.assertEqual(messages[-1]["task_id"], task_id)
            self.assertEqual(
                store.artifact_for_message("labagent", messages[-1]["id"], 0)["kind"],
                "image",
            )

    def test_routes_and_public_artifact_shape(self):
        self.assertEqual(room_messages_route("/api/rooms/labagent/messages"), "labagent")
        self.assertEqual(room_invites_route("/api/rooms/labagent/invites"), "labagent")
        self.assertEqual(
            room_artifact_route("/api/rooms/labagent/artifacts/12/3"),
            ("labagent", 12, 3),
        )
        shaped = room_message_shape(
            {
                "id": 12,
                "room_id": "labagent",
                "role": "assistant",
                "artifacts": [
                    {
                        "path": "agent/tasks/t/artifacts/result.step",
                        "title": "Editable STEP",
                        "kind": "cad",
                    }
                ],
            }
        )
        self.assertNotIn("path", shaped["artifacts"][0])
        self.assertEqual(
            shaped["artifacts"][0]["url"],
            "/api/rooms/labagent/artifacts/12/0",
        )

    def test_participant_options_are_plan_only(self):
        options = room_agent_options(
            {"model": "gpt-5.6-sol", "mode": "execute", "timeout_seconds": 3600},
            {"agent": {"fallback_to_aginti": True}},
            access_role="participant",
        )

        self.assertEqual(options["mode"], "plan")
        self.assertEqual(options["timeout_seconds"], 900)
        self.assertEqual(options["_room_access_role"], "participant")


if __name__ == "__main__":
    unittest.main()
