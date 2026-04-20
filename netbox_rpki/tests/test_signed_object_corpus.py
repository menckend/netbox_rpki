"""Corpus-driven tests for RPKI signed-object parser functions.

Each test class covers one parser function from provider_sync_krill and
drives it against the golden corpus defined in signed_object_corpus.py.
Tests are organised by artifact category: VALID, STALE, EDGE_CASE, MALFORMED.

All test classes use SimpleTestCase (no database required).
"""

from django.test import SimpleTestCase

from netbox_rpki.services.provider_sync_krill import (
    _infer_signed_object_type,
    _load_cms_certificates,
    _load_cms_signed_data,
    _load_der_certificate,
    _parse_cms_crl_metadata,
    _parse_cms_manifest_metadata,
    parse_krill_signed_object_records,
)
from netbox_rpki.tests.signed_object_corpus import (
    CORPUS_ASPA_CMS_VALID_B64,
    CORPUS_CA_CERT_VALID_B64,
    CORPUS_CMS_NON_MANIFEST_B64,
    CORPUS_CRL_FRESH_B64,
    CORPUS_CRL_NO_NUMBER_B64,
    CORPUS_CRL_STALE_B64,
    CORPUS_CRL_WITH_REVOKED_B64,
    CORPUS_EE_CERT_VALID_B64,
    CORPUS_EMPTY_STRING,
    CORPUS_INVALID_BASE64,
    CORPUS_MANIFEST_EMPTY_FILES_B64,
    CORPUS_MANIFEST_STALE_B64,
    CORPUS_MANIFEST_VALID_B64,
    CORPUS_RANDOM_BYTES_B64,
    CORPUS_ROA_CMS_VALID_B64,
    CORPUS_TRUNCATED_DER_B64,
)


class DerCertificateCorpusTestCase(SimpleTestCase):
    """_load_der_certificate against the golden corpus."""

    # -- VALID ---------------------------------------------------------------

    def test_valid_ca_certificate_parses_successfully(self):
        cert = _load_der_certificate(CORPUS_CA_CERT_VALID_B64)
        self.assertIsNotNone(cert)
        self.assertIn('RPKI Corpus CA', cert.subject.rfc4514_string())

    def test_valid_ee_certificate_has_correct_issuer(self):
        cert = _load_der_certificate(CORPUS_EE_CERT_VALID_B64)
        self.assertIsNotNone(cert)
        self.assertIn('RPKI Corpus CA', cert.issuer.rfc4514_string())
        self.assertIn('RPKI Corpus ROA EE', cert.subject.rfc4514_string())

    # -- MALFORMED -----------------------------------------------------------

    def test_empty_string_returns_none(self):
        self.assertIsNone(_load_der_certificate(CORPUS_EMPTY_STRING))

    def test_invalid_base64_returns_none(self):
        self.assertIsNone(_load_der_certificate(CORPUS_INVALID_BASE64))

    def test_random_bytes_returns_none(self):
        self.assertIsNone(_load_der_certificate(CORPUS_RANDOM_BYTES_B64))

    def test_truncated_der_returns_none(self):
        self.assertIsNone(_load_der_certificate(CORPUS_TRUNCATED_DER_B64))


class CrlCorpusTestCase(SimpleTestCase):
    """_parse_cms_crl_metadata against the golden corpus."""

    # -- VALID ---------------------------------------------------------------

    def test_fresh_crl_reports_fresh_status(self):
        meta = _parse_cms_crl_metadata(CORPUS_CRL_FRESH_B64)
        self.assertEqual(meta.get('freshness_status'), 'fresh')

    def test_fresh_crl_has_zero_revoked_count(self):
        meta = _parse_cms_crl_metadata(CORPUS_CRL_FRESH_B64)
        self.assertEqual(meta.get('revoked_count'), 0)

    def test_fresh_crl_exposes_crl_number(self):
        meta = _parse_cms_crl_metadata(CORPUS_CRL_FRESH_B64)
        self.assertEqual(meta.get('crl_number'), '1')

    def test_fresh_crl_has_issuer_and_timestamps(self):
        meta = _parse_cms_crl_metadata(CORPUS_CRL_FRESH_B64)
        self.assertIn('issuer', meta)
        self.assertIn('this_update', meta)
        self.assertIn('next_update', meta)

    def test_crl_with_revoked_entry_returns_correct_count(self):
        meta = _parse_cms_crl_metadata(CORPUS_CRL_WITH_REVOKED_B64)
        self.assertEqual(meta.get('revoked_count'), 1)

    def test_crl_with_revoked_entry_exposes_crl_number(self):
        meta = _parse_cms_crl_metadata(CORPUS_CRL_WITH_REVOKED_B64)
        self.assertEqual(meta.get('crl_number'), '5')

    def test_crl_with_revoked_entry_is_fresh(self):
        meta = _parse_cms_crl_metadata(CORPUS_CRL_WITH_REVOKED_B64)
        self.assertEqual(meta.get('freshness_status'), 'fresh')

    # -- STALE ---------------------------------------------------------------

    def test_stale_crl_reports_stale_status(self):
        meta = _parse_cms_crl_metadata(CORPUS_CRL_STALE_B64)
        self.assertEqual(meta.get('freshness_status'), 'stale')

    # -- EDGE CASE -----------------------------------------------------------

    def test_crl_without_crl_number_extension_returns_empty_string(self):
        meta = _parse_cms_crl_metadata(CORPUS_CRL_NO_NUMBER_B64)
        self.assertEqual(meta.get('crl_number'), '')

    def test_crl_without_crl_number_is_still_fresh(self):
        meta = _parse_cms_crl_metadata(CORPUS_CRL_NO_NUMBER_B64)
        self.assertEqual(meta.get('freshness_status'), 'fresh')

    # -- MALFORMED -----------------------------------------------------------

    def test_empty_string_returns_empty_dict(self):
        self.assertEqual(_parse_cms_crl_metadata(CORPUS_EMPTY_STRING), {})

    def test_invalid_base64_returns_empty_dict(self):
        self.assertEqual(_parse_cms_crl_metadata(CORPUS_INVALID_BASE64), {})

    def test_random_bytes_returns_empty_dict(self):
        self.assertEqual(_parse_cms_crl_metadata(CORPUS_RANDOM_BYTES_B64), {})

    def test_truncated_der_returns_empty_dict(self):
        self.assertEqual(_parse_cms_crl_metadata(CORPUS_TRUNCATED_DER_B64), {})


class ManifestCorpusTestCase(SimpleTestCase):
    """_parse_cms_manifest_metadata against the golden corpus."""

    # -- VALID ---------------------------------------------------------------

    def test_valid_manifest_returns_correct_manifest_number(self):
        meta = _parse_cms_manifest_metadata(CORPUS_MANIFEST_VALID_B64)
        self.assertEqual(meta.get('manifest_number'), 42)

    def test_valid_manifest_returns_two_file_entries(self):
        meta = _parse_cms_manifest_metadata(CORPUS_MANIFEST_VALID_B64)
        self.assertEqual(len(meta.get('file_entries', [])), 2)

    def test_valid_manifest_file_names_are_correct(self):
        meta = _parse_cms_manifest_metadata(CORPUS_MANIFEST_VALID_B64)
        names = [e['file'] for e in meta.get('file_entries', [])]
        self.assertIn('corpus.roa', names)
        self.assertIn('corpus.crl', names)

    def test_valid_manifest_exposes_timestamps(self):
        meta = _parse_cms_manifest_metadata(CORPUS_MANIFEST_VALID_B64)
        self.assertIn('this_update', meta)
        self.assertIn('next_update', meta)
        self.assertTrue(meta['this_update'])
        self.assertTrue(meta['next_update'])

    def test_valid_manifest_embedded_certificate_count(self):
        meta = _parse_cms_manifest_metadata(CORPUS_MANIFEST_VALID_B64)
        self.assertEqual(meta.get('embedded_certificate_count'), 1)

    # -- STALE ---------------------------------------------------------------

    def test_stale_manifest_parses_without_error(self):
        meta = _parse_cms_manifest_metadata(CORPUS_MANIFEST_STALE_B64)
        self.assertEqual(meta.get('manifest_number'), 1)

    def test_stale_manifest_next_update_contains_2024(self):
        meta = _parse_cms_manifest_metadata(CORPUS_MANIFEST_STALE_B64)
        self.assertIn('2024', meta.get('next_update', ''))

    # -- EDGE CASE -----------------------------------------------------------

    def test_manifest_with_empty_file_list_returns_no_entries(self):
        meta = _parse_cms_manifest_metadata(CORPUS_MANIFEST_EMPTY_FILES_B64)
        self.assertEqual(meta.get('manifest_number'), 0)
        self.assertEqual(meta.get('file_entries'), [])

    def test_cms_with_non_manifest_payload_returns_empty_dict(self):
        self.assertEqual(_parse_cms_manifest_metadata(CORPUS_CMS_NON_MANIFEST_B64), {})

    # -- MALFORMED -----------------------------------------------------------

    def test_empty_string_returns_empty_dict(self):
        self.assertEqual(_parse_cms_manifest_metadata(CORPUS_EMPTY_STRING), {})

    def test_invalid_base64_returns_empty_dict(self):
        self.assertEqual(_parse_cms_manifest_metadata(CORPUS_INVALID_BASE64), {})

    def test_random_bytes_returns_empty_dict(self):
        self.assertEqual(_parse_cms_manifest_metadata(CORPUS_RANDOM_BYTES_B64), {})


class CmsSignedDataCorpusTestCase(SimpleTestCase):
    """_load_cms_signed_data and _load_cms_certificates against the golden corpus."""

    # -- VALID ---------------------------------------------------------------

    def test_roa_cms_yields_signed_data(self):
        sd = _load_cms_signed_data(CORPUS_ROA_CMS_VALID_B64)
        self.assertIsNotNone(sd)

    def test_aspa_cms_yields_signed_data(self):
        sd = _load_cms_signed_data(CORPUS_ASPA_CMS_VALID_B64)
        self.assertIsNotNone(sd)

    def test_manifest_cms_yields_signed_data(self):
        sd = _load_cms_signed_data(CORPUS_MANIFEST_VALID_B64)
        self.assertIsNotNone(sd)

    def test_roa_cms_contains_one_embedded_certificate(self):
        certs = _load_cms_certificates(CORPUS_ROA_CMS_VALID_B64)
        self.assertEqual(len(certs), 1)

    def test_manifest_cms_contains_one_embedded_certificate(self):
        certs = _load_cms_certificates(CORPUS_MANIFEST_VALID_B64)
        self.assertEqual(len(certs), 1)

    def test_aspa_cms_contains_one_embedded_certificate(self):
        certs = _load_cms_certificates(CORPUS_ASPA_CMS_VALID_B64)
        self.assertEqual(len(certs), 1)

    # -- MALFORMED -----------------------------------------------------------

    def test_empty_string_signed_data_returns_none(self):
        self.assertIsNone(_load_cms_signed_data(CORPUS_EMPTY_STRING))

    def test_invalid_base64_signed_data_returns_none(self):
        self.assertIsNone(_load_cms_signed_data(CORPUS_INVALID_BASE64))

    def test_random_bytes_signed_data_returns_none(self):
        self.assertIsNone(_load_cms_signed_data(CORPUS_RANDOM_BYTES_B64))

    def test_truncated_der_signed_data_returns_none(self):
        self.assertIsNone(_load_cms_signed_data(CORPUS_TRUNCATED_DER_B64))

    def test_empty_string_certificates_returns_empty_list(self):
        self.assertEqual(_load_cms_certificates(CORPUS_EMPTY_STRING), [])

    def test_invalid_base64_certificates_returns_empty_list(self):
        self.assertEqual(_load_cms_certificates(CORPUS_INVALID_BASE64), [])


class InferSignedObjectTypeCorpusTestCase(SimpleTestCase):
    """_infer_signed_object_type URI extension inference."""

    def setUp(self):
        from netbox_rpki import models as m
        self.m = m

    def test_roa_extension_inferred(self):
        self.assertEqual(
            _infer_signed_object_type('rsync://repo.example/pub/foo.roa'),
            self.m.SignedObjectType.ROA,
        )

    def test_mft_extension_inferred(self):
        self.assertEqual(
            _infer_signed_object_type('rsync://repo.example/pub/bar.mft'),
            self.m.SignedObjectType.MANIFEST,
        )

    def test_crl_extension_inferred(self):
        self.assertEqual(
            _infer_signed_object_type('rsync://repo.example/pub/baz.crl'),
            self.m.SignedObjectType.CRL,
        )

    def test_asa_extension_inferred(self):
        self.assertEqual(
            _infer_signed_object_type('rsync://repo.example/pub/qux.asa'),
            self.m.SignedObjectType.ASPA,
        )

    def test_aspa_extension_inferred(self):
        self.assertEqual(
            _infer_signed_object_type('rsync://repo.example/pub/qux.aspa'),
            self.m.SignedObjectType.ASPA,
        )

    def test_rsc_extension_inferred(self):
        self.assertEqual(
            _infer_signed_object_type('rsync://repo.example/pub/foo.rsc'),
            self.m.SignedObjectType.RSC,
        )

    def test_tak_extension_inferred(self):
        self.assertEqual(
            _infer_signed_object_type('rsync://repo.example/pub/foo.tak'),
            self.m.SignedObjectType.TAK,
        )

    def test_unknown_extension_returns_other(self):
        self.assertEqual(
            _infer_signed_object_type('rsync://repo.example/pub/foo.xyz'),
            self.m.SignedObjectType.OTHER,
        )

    def test_empty_uri_returns_other(self):
        self.assertEqual(
            _infer_signed_object_type(''),
            self.m.SignedObjectType.OTHER,
        )

    def test_uppercase_extension_inferred_case_insensitively(self):
        self.assertEqual(
            _infer_signed_object_type('rsync://repo.example/pub/FOO.ROA'),
            self.m.SignedObjectType.ROA,
        )


class ParseSignedObjectRecordsCorpusTestCase(SimpleTestCase):
    """parse_krill_signed_object_records end-to-end, corpus-driven."""

    def test_empty_payloads_return_empty_list(self):
        self.assertEqual(parse_krill_signed_object_records(), [])

    def test_none_payloads_return_empty_list(self):
        self.assertEqual(parse_krill_signed_object_records(None, None), [])

    def test_mixed_object_types_parsed_from_repo_status(self):
        from netbox_rpki import models as m

        repo_details = {'repo_info': {'sia_base': 'rsync://repo.example/pub/'}}
        repo_status = {
            'published': [
                {'uri': 'rsync://repo.example/pub/foo.roa', 'base64': CORPUS_ROA_CMS_VALID_B64},
                {'uri': 'rsync://repo.example/pub/bar.mft', 'base64': CORPUS_MANIFEST_VALID_B64},
                {'uri': 'rsync://repo.example/pub/baz.crl', 'base64': CORPUS_CRL_FRESH_B64},
                {'uri': 'rsync://repo.example/pub/qux.asa', 'base64': CORPUS_ASPA_CMS_VALID_B64},
            ]
        }
        records = parse_krill_signed_object_records(repo_details, repo_status)
        self.assertEqual(len(records), 4)
        types = {r.signed_object_type for r in records}
        self.assertIn(m.SignedObjectType.ROA, types)
        self.assertIn(m.SignedObjectType.MANIFEST, types)
        self.assertIn(m.SignedObjectType.CRL, types)
        self.assertIn(m.SignedObjectType.ASPA, types)

    def test_object_with_empty_uri_and_body_is_skipped(self):
        repo_details = {'repo_info': {'sia_base': 'rsync://repo.example/pub/'}}
        repo_status = {'published': [{'uri': '', 'base64': ''}]}
        records = parse_krill_signed_object_records(repo_details, repo_status)
        self.assertEqual(len(records), 0)

    def test_publication_uri_extracted_from_repo_info_sia_base(self):
        repo_details = {'repo_info': {'sia_base': 'rsync://corpus.example/pub/'}}
        repo_status = {
            'published': [
                {'uri': 'rsync://corpus.example/pub/x.roa', 'base64': CORPUS_ROA_CMS_VALID_B64},
            ]
        }
        records = parse_krill_signed_object_records(repo_details, repo_status)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].publication_uri, 'rsync://corpus.example/pub/')

    def test_signed_object_uri_preserved_on_record(self):
        repo_details = {'repo_info': {'sia_base': 'rsync://corpus.example/pub/'}}
        repo_status = {
            'published': [
                {'uri': 'rsync://corpus.example/pub/test.mft', 'base64': CORPUS_MANIFEST_VALID_B64},
            ]
        }
        records = parse_krill_signed_object_records(repo_details, repo_status)
        self.assertEqual(records[0].signed_object_uri, 'rsync://corpus.example/pub/test.mft')

    def test_object_hash_is_populated(self):
        repo_details = {'repo_info': {'sia_base': 'rsync://corpus.example/pub/'}}
        repo_status = {
            'published': [
                {'uri': 'rsync://corpus.example/pub/test.crl', 'base64': CORPUS_CRL_FRESH_B64},
            ]
        }
        records = parse_krill_signed_object_records(repo_details, repo_status)
        self.assertTrue(records[0].object_hash)

    def test_malformed_body_still_produces_record_with_uri(self):
        """Objects with unparseable bodies still appear in the record list."""
        repo_details = {'repo_info': {'sia_base': 'rsync://corpus.example/pub/'}}
        repo_status = {
            'published': [
                {'uri': 'rsync://corpus.example/pub/bad.roa', 'base64': CORPUS_INVALID_BASE64},
            ]
        }
        records = parse_krill_signed_object_records(repo_details, repo_status)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].signed_object_uri, 'rsync://corpus.example/pub/bad.roa')
