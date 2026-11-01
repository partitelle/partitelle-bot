import unittest
from telegram import Update
from unittest.mock import MagicMock
from datetime import datetime
from domain import Match, Participant, Teams
from domain.schedule import TIMEZONE
from utils.utils import (
    get_sender_mention,
    get_sender_name,
    flatten_args,
    join_names,
    format_teams,
    format_summary,
    already_in_message,
)


def _participants(raw):
    return [
        Participant(
            p.removesuffix("%is%maybe%present"), p.endswith("%is%maybe%present")
        )
        for p in raw
    ]


class TestUtils(unittest.TestCase):
    def test_get_sender_name(self):
        mock_update = MagicMock(spec=Update)
        mock_update.message.from_user.username = "JohnDoe"
        self.assertEqual(get_sender_name(mock_update), "johndoe")

    def test_get_sender_name_and_mention_without_username(self):
        mock_update = MagicMock(spec=Update)
        user = mock_update.message.from_user
        user.username = None
        user.first_name = "Luca"
        user.last_name = None
        self.assertEqual(get_sender_name(mock_update), "Luca")
        self.assertEqual(get_sender_mention(mock_update), "Luca")
        user.last_name = "Bianchi"
        self.assertEqual(get_sender_name(mock_update), "Luca Bianchi")
        self.assertEqual(get_sender_mention(mock_update), "Luca Bianchi")

    def test_get_sender_mention_with_username(self):
        mock_update = MagicMock(spec=Update)
        user = mock_update.message.from_user
        user.username = "JohnDoe"
        user.first_name = "John"
        user.last_name = "Doe"
        self.assertEqual(get_sender_mention(mock_update), "@johndoe")

    def test_get_sender_name_and_mention_without_sender(self):
        mock_update = MagicMock(spec=Update)
        mock_update.message.from_user = None
        self.assertIsNone(get_sender_name(mock_update))
        self.assertIsNone(get_sender_mention(mock_update))

    def test_flatten_args(self):
        # Test case 1: Single argument
        args = ["Wednesday"]
        self.assertEqual(flatten_args(args), "Wednesday")

        # Test case 2: Multiple arguments
        args = ["Wednesday", "01/01/2000"]
        self.assertEqual(flatten_args(args), "Wednesday 01/01/2000")

        # Test case 3: No arguments
        args = []
        self.assertEqual(flatten_args(args), "")

    def test_join_names(self):
        self.assertEqual(join_names([]), "")
        self.assertEqual(join_names(["a"]), "a")
        self.assertEqual(join_names(["a", "b"]), "a e b")
        self.assertEqual(join_names(["a", "b", "c"]), "a, b e c")
        self.assertEqual(join_names(["a", "b", "c", "d"]), "a, b, c e d")

    def test_already_in_message(self):
        self.assertEqual(
            already_in_message(
                Match(1, [Participant("a"), Participant("b")], target=2)
            ),
            "Siete già in 2",
        )
        self.assertEqual(
            already_in_message(
                Match(
                    1,
                    [Participant("a"), Participant("b"), Participant("c", True)],
                    target=2,
                )
            ),
            "Siete già in 2 (1 in forse)",
        )

    def test_format_teams(self):
        # Test case 1: Teams are empty
        teams = Teams((), ())
        with self.assertRaises(Exception):
            format_teams(teams)

        # Test case 2: Teams are not empty
        teams = Teams(("JohnDoe", "JaneDoe", "Alice"), ("Bob", "Charlie", "Eve"))
        self.assertEqual(
            format_teams(teams),
            "*SQUADRA NERA* \n - JohnDoe\n - JaneDoe\n - Alice\n\n*SQUADRA BIANCA* \n - Bob\n - Charlie\n - Eve\n",
        )

    def test_format_summary(self):
        # Test case 1: No players
        names = []
        starts = datetime(2026, 10, 28, 20, 0, tzinfo=TIMEZONE)
        target = 6
        default_message = "Default message"
        pitch = "Pitch"
        expected_output = (
            "*GIORNO*: Mercoledì 28/10/2026 | 20:00\n\n"
            "1. ❌\n"
            "2. ❌\n"
            "3. ❌\n"
            "4. ❌\n"
            "5. ❌\n"
            "6. ❌\n\n"
            "Default message\n\n"
            "*CAMPO*: \n"
            "Pitch"
        )
        self.assertEqual(
            format_summary(
                Match(
                    1,
                    _participants(names),
                    starts,
                    target,
                    default_message,
                    pitch,
                )
            ),
            expected_output,
        )

        # Test case 2: Full players present
        names = ["JohnDoe", "JaneDoe", "Alice", "Bob", "Charlie", "Eve"]
        starts = datetime(2026, 10, 28, 20, 0, tzinfo=TIMEZONE)
        target = 6
        default_message = "Default message"
        pitch = "Pitch"
        expected_output = (
            "*GIORNO*: Mercoledì 28/10/2026 | 20:00\n\n"
            "1. JohnDoe ✅\n"
            "2. JaneDoe ✅\n"
            "3. Alice ✅\n"
            "4. Bob ✅\n"
            "5. Charlie ✅\n"
            "6. Eve ✅\n\n"
            "Default message\n\n"
            "*CAMPO*: \n"
            "Pitch"
        )
        self.assertEqual(
            format_summary(
                Match(
                    1,
                    _participants(names),
                    starts,
                    target,
                    default_message,
                    pitch,
                )
            ),
            expected_output,
        )

        # Test case 3: Some players present
        names = ["JohnDoe", "JaneDoe", "Alice", "Bob", "Charlie"]
        starts = datetime(2026, 10, 28, 20, 0, tzinfo=TIMEZONE)
        target = 6
        default_message = "Default message"
        pitch = "Pitch"
        expected_output = (
            "*GIORNO*: Mercoledì 28/10/2026 | 20:00\n\n"
            "1. JohnDoe ✅\n"
            "2. JaneDoe ✅\n"
            "3. Alice ✅\n"
            "4. Bob ✅\n"
            "5. Charlie ✅\n"
            "6. ❌\n\n"
            "Default message\n\n"
            "*CAMPO*: \n"
            "Pitch"
        )
        self.assertEqual(
            format_summary(
                Match(
                    1,
                    _participants(names),
                    starts,
                    target,
                    default_message,
                    pitch,
                )
            ),
            expected_output,
        )

        # Test case 4: Some players present, some maybe
        names = [
            "JohnDoe",
            "JaneDoe",
            "Alice%is%maybe%present",
            "Bob",
            "Charlie%is%maybe%present",
        ]
        starts = datetime(2026, 10, 28, 20, 0, tzinfo=TIMEZONE)
        target = 6
        default_message = "Default message"
        pitch = "Pitch"
        expected_output = (
            "*GIORNO*: Mercoledì 28/10/2026 | 20:00\n\n"
            "1. JohnDoe ✅\n"
            "2. JaneDoe ✅\n"
            "3. Alice ❓\n"
            "4. Bob ✅\n"
            "5. Charlie ❓\n"
            "6. ❌\n\n"
            "Default message\n\n"
            "*CAMPO*: \n"
            "Pitch"
        )
        self.assertEqual(
            format_summary(
                Match(
                    1,
                    _participants(names),
                    starts,
                    target,
                    default_message,
                    pitch,
                )
            ),
            expected_output,
        )


if __name__ == "__main__":
    unittest.main()
