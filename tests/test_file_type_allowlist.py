import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from assistant.file_type_allowlist import (
    FileSignerInfo,
    FileTypeAllowlistError,
    FileTypeAllowlistStore,
)


class FileTypeAllowlistTests(unittest.TestCase):
    def test_allow_and_disallow_extension(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = FileTypeAllowlistStore(Path(temp_dir) / "file_types.json")

            allowed = store.allow_extension("PDF")
            extensions = store.list_extensions()
            removed = store.disallow_extension(".pdf")

        self.assertEqual(allowed, ".pdf")
        self.assertEqual(extensions, [".pdf"])
        self.assertEqual(removed, ".pdf")

    def test_summary_mentions_empty_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = FileTypeAllowlistStore(Path(temp_dir) / "file_types.json")

            text = store.summary()

        self.assertIn("File type allowlist: none", text)
        self.assertIn("blocked", text)

    def test_invalid_extension_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = FileTypeAllowlistStore(Path(temp_dir) / "file_types.json")

            with self.assertRaises(FileTypeAllowlistError):
                store.allow_extension(".p df")

    def test_trust_policy_can_store_sources_and_signers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = FileTypeAllowlistStore(Path(temp_dir) / "file_types.json")
            store.allow_extension("pdf")

            policy_sources = store.set_trusted_sources(".pdf", ["C:/Trusted Docs"])
            policy_signers = store.set_trusted_signers("pdf", ["Microsoft", "Contoso"])
            policy_thumbprints = store.set_pinned_thumbprints(
                ".pdf",
                ["11 22 33 44 55 66 77 88 99 00 AA BB CC DD EE FF 00 11 22 33"],
            )
            policy_issuers = store.set_trusted_issuers(".pdf", ["Microsoft Root CA"])
            policy_validity = store.set_validity_requirement(".pdf", True)
            policy_revocation = store.set_revocation_requirement(".pdf", True, revocation_mode="ocsp")
            summary = store.trust_policy_summary(".pdf")

        self.assertEqual(policy_sources.trusted_sources, ("C:/Trusted Docs",))
        self.assertEqual(policy_signers.trusted_signers, ("Microsoft", "Contoso"))
        self.assertEqual(
            policy_thumbprints.pinned_thumbprints,
            ("11223344556677889900AABBCCDDEEFF00112233",),
        )
        self.assertEqual(policy_issuers.trusted_issuers, ("Microsoft Root CA",))
        self.assertTrue(policy_validity.require_valid_certificate)
        self.assertTrue(policy_revocation.require_revocation_check)
        self.assertEqual(policy_revocation.revocation_mode, "ocsp")
        self.assertIn("Trust policy for .pdf", summary)
        self.assertIn("Trusted sources", summary)
        self.assertIn("Trusted signer tokens", summary)
        self.assertIn("Pinned certificate thumbprints", summary)
        self.assertIn("Trusted issuer tokens", summary)
        self.assertIn("Certificate validity requirement: required", summary)
        self.assertIn("Certificate revocation check: required (mode: ocsp)", summary)

    @patch(
        "assistant.file_type_allowlist._authenticode_revocation_status",
        return_value=(True, "good (ocsp)"),
    )
    def test_trust_signal_evaluation_uses_configured_revocation_mode(self, mock_revocation) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = root / "report.pdf"
            target.write_text("ok", encoding="utf-8")
            store = FileTypeAllowlistStore(root / "file_types.json")
            store.allow_extension(".pdf")
            store.set_revocation_requirement(".pdf", True, revocation_mode="ocsp")

            result = store.evaluate_trust_signals(".pdf", target)

        self.assertTrue(result.passed)
        mock_revocation.assert_called_once_with(target, "ocsp")
        self.assertTrue(any("Revocation mode ocsp allowed launch" in note for note in result.notes))
        self.assertTrue(any("OCSP endpoint must be advertised" in note for note in result.notes))

    @patch("assistant.file_type_allowlist._authenticode_revocation_status")
    def test_trust_signal_evaluation_skips_revocation_when_not_required(self, mock_revocation) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = root / "report.pdf"
            target.write_text("ok", encoding="utf-8")
            store = FileTypeAllowlistStore(root / "file_types.json")
            store.allow_extension(".pdf")
            store.set_revocation_requirement(".pdf", False)

            result = store.evaluate_trust_signals(".pdf", target)

        self.assertTrue(result.passed)
        mock_revocation.assert_not_called()

    @patch(
        "assistant.file_type_allowlist._authenticode_signer_info",
        return_value=FileSignerInfo(
            subject="CN=Microsoft Corporation",
            thumbprint="11223344556677889900AABBCCDDEEFF00112233",
            issuer="CN=Microsoft Root CA",
            not_before=datetime.now(UTC) - timedelta(days=1),
            not_after=datetime.now(UTC) + timedelta(days=1),
        ),
    )
    def test_trust_signal_evaluation_uses_source_and_signer_checks(self, _mock_signer) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            trusted = root / "trusted"
            trusted.mkdir()
            target = trusted / "report.pdf"
            target.write_text("ok", encoding="utf-8")
            store = FileTypeAllowlistStore(root / "file_types.json")
            store.allow_extension(".pdf")
            store.set_trusted_sources(".pdf", [str(trusted)])
            store.set_trusted_signers(".pdf", ["Microsoft"])
            store.set_pinned_thumbprints(".pdf", ["11223344556677889900AABBCCDDEEFF00112233"])
            store.set_trusted_issuers(".pdf", ["Microsoft Root"])
            store.set_validity_requirement(".pdf", True)

            result = store.evaluate_trust_signals(".pdf", target)

        self.assertTrue(result.passed)
        self.assertIn("Trust checks passed.", result.notes)

    @patch(
        "assistant.file_type_allowlist._authenticode_signer_info",
        return_value=FileSignerInfo(subject=None, thumbprint=None),
    )
    def test_trust_signal_evaluation_blocks_when_signer_required_but_missing(self, _mock_signer) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = root / "report.pdf"
            target.write_text("ok", encoding="utf-8")
            store = FileTypeAllowlistStore(root / "file_types.json")
            store.allow_extension(".pdf")
            store.set_trusted_signers(".pdf", ["Microsoft"])

            result = store.evaluate_trust_signals(".pdf", target)

        self.assertFalse(result.passed)
        self.assertTrue(any(note.startswith("BLOCKED:") for note in result.notes))

    @patch(
        "assistant.file_type_allowlist._authenticode_signer_info",
        return_value=FileSignerInfo(
            subject="CN=Microsoft Corporation",
            thumbprint="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
            issuer="CN=Microsoft Root CA",
            not_before=datetime.now(UTC) - timedelta(days=1),
            not_after=datetime.now(UTC) + timedelta(days=1),
        ),
    )
    def test_trust_signal_evaluation_blocks_on_thumbprint_mismatch(self, _mock_signer) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = root / "report.pdf"
            target.write_text("ok", encoding="utf-8")
            store = FileTypeAllowlistStore(root / "file_types.json")
            store.allow_extension(".pdf")
            store.set_pinned_thumbprints(".pdf", ["11223344556677889900AABBCCDDEEFF00112233"])

            result = store.evaluate_trust_signals(".pdf", target)

        self.assertFalse(result.passed)
        self.assertTrue(any("thumbprint" in note.casefold() for note in result.notes))

    @patch(
        "assistant.file_type_allowlist._authenticode_signer_info",
        return_value=FileSignerInfo(
            subject="CN=Microsoft Corporation",
            thumbprint="11223344556677889900AABBCCDDEEFF00112233",
            issuer="CN=Unknown Issuer",
            not_before=datetime.now(UTC) - timedelta(days=1),
            not_after=datetime.now(UTC) + timedelta(days=1),
        ),
    )
    def test_trust_signal_evaluation_blocks_on_issuer_mismatch(self, _mock_signer) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = root / "report.pdf"
            target.write_text("ok", encoding="utf-8")
            store = FileTypeAllowlistStore(root / "file_types.json")
            store.allow_extension(".pdf")
            store.set_trusted_issuers(".pdf", ["Microsoft Root"])

            result = store.evaluate_trust_signals(".pdf", target)

        self.assertFalse(result.passed)
        self.assertTrue(any("issuer" in note.casefold() for note in result.notes))

    @patch(
        "assistant.file_type_allowlist._authenticode_signer_info",
        return_value=FileSignerInfo(
            subject="CN=Microsoft Corporation",
            thumbprint="11223344556677889900AABBCCDDEEFF00112233",
            issuer="CN=Microsoft Root CA",
            not_before=datetime.now(UTC) + timedelta(days=1),
            not_after=datetime.now(UTC) + timedelta(days=2),
        ),
    )
    def test_trust_signal_evaluation_blocks_on_invalid_certificate_dates(self, _mock_signer) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = root / "report.pdf"
            target.write_text("ok", encoding="utf-8")
            store = FileTypeAllowlistStore(root / "file_types.json")
            store.allow_extension(".pdf")
            store.set_validity_requirement(".pdf", True)

            result = store.evaluate_trust_signals(".pdf", target)

        self.assertFalse(result.passed)
        self.assertTrue(any("not currently valid" in note.casefold() for note in result.notes))

    @patch(
        "assistant.file_type_allowlist._authenticode_revocation_status",
        return_value=(False, "Revoked"),
    )
    def test_trust_signal_evaluation_blocks_on_failed_revocation_check(self, _mock_revocation) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = root / "report.pdf"
            target.write_text("ok", encoding="utf-8")
            store = FileTypeAllowlistStore(root / "file_types.json")
            store.allow_extension(".pdf")
            store.set_revocation_requirement(".pdf", True)

            result = store.evaluate_trust_signals(".pdf", target)

        self.assertFalse(result.passed)
        self.assertTrue(any("revocation" in note.casefold() for note in result.notes))
        self.assertTrue(any("revocation mode online blocked launch" in note.casefold() for note in result.notes))

    @patch(
        "assistant.file_type_allowlist._authenticode_revocation_status",
        return_value=(None, "network unavailable"),
    )
    def test_trust_signal_evaluation_explains_indeterminate_revocation_mode(self, _mock_revocation) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = root / "report.pdf"
            target.write_text("ok", encoding="utf-8")
            store = FileTypeAllowlistStore(root / "file_types.json")
            store.allow_extension(".pdf")
            store.set_revocation_requirement(".pdf", True, revocation_mode="both")

            result = store.evaluate_trust_signals(".pdf", target)

        self.assertFalse(result.passed)
        self.assertTrue(any("revocation mode both could not determine" in note.casefold() for note in result.notes))
        self.assertTrue(any("both OCSP and CRL" in note for note in result.notes))


if __name__ == "__main__":
    unittest.main()
