import unittest

from pydantic import ValidationError

from app.schemas.user import RegisterIn


class RegistrationInputLimitTests(unittest.TestCase):
    @staticmethod
    def registration_data(**overrides):
        data = {
            "username": "valid-user",
            "phone": "13900000091",
            "password": "valid-password",
            "invite_code": "WODTEST01",
            "captcha_key": "test-key",
            "captcha_code": "A2BC",
        }
        data.update(overrides)
        return data

    def test_registration_accepts_field_boundaries(self):
        minimums = RegisterIn(**self.registration_data(
            username="ab",
            password="123456",
            invite_code="",
        ))
        maximums = RegisterIn(**self.registration_data(
            username="u" * 64,
            password="p" * 64,
            invite_code=f"  {'i' * 16}  ",
        ))

        self.assertEqual(len(minimums.username), 2)
        self.assertEqual(len(minimums.password), 6)
        self.assertEqual(len(maximums.username), 64)
        self.assertEqual(len(maximums.password), 64)
        self.assertEqual(len(maximums.invite_code or ""), 16)
        self.assertEqual(maximums.invite_code, "I" * 16)

    def test_registration_rejects_values_outside_field_boundaries(self):
        invalid_values = (
            {"username": "u"},
            {"username": "u" * 65},
            {"password": "p" * 5},
            {"password": "p" * 65},
            {"invite_code": "I" * 17},
        )

        for overrides in invalid_values:
            with self.subTest(overrides=overrides), self.assertRaises(ValidationError):
                RegisterIn(**self.registration_data(**overrides))

    def test_registration_normalizes_optional_invite_code(self):
        self.assertIsNone(RegisterIn(**self.registration_data(invite_code=None)).invite_code)
        self.assertIsNone(RegisterIn(**self.registration_data(invite_code="")).invite_code)
        self.assertIsNone(RegisterIn(**self.registration_data(invite_code="   ")).invite_code)
        self.assertEqual(
            RegisterIn(**self.registration_data(invite_code="  wodtest01  ")).invite_code,
            "WODTEST01",
        )


if __name__ == "__main__":
    unittest.main()
