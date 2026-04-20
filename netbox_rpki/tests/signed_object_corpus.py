"""Golden fixture corpus for RPKI signed objects and repository metadata.

This module provides deterministic synthetic artifacts for testing parser and
ingest logic against standards-shaped inputs. Each CORPUS_* constant documents
its provenance (how it was constructed) and intent (which parser behaviour it
exercises).

Artifact categories
-------------------
VALID     - Well-formed; parsers must accept and return complete metadata.
STALE     - Chronologically expired; parsers note the state but still parse.
EDGE_CASE - Boundary conditions: empty file lists, absent optional extensions.
MALFORMED - Structurally invalid; parsers must return empty / None, never raise.

Generation
----------
Certificate and CRL artifacts are built at import time using the ``cryptography``
library; no external files or network access are required.

RFC 6486 Manifest DER constants are pre-encoded to avoid pyasn1 0.6.x class-level
schema mutation issues that arise when ``rfc6486.Manifest()`` is called multiple
times in the same process.  Each constant was generated once using pyasn1, verified
to decode correctly, and then hardcoded.  The wrapping CMS signatures ARE generated
at import time so that they exercise the full CMS path.
"""

from __future__ import annotations

import base64
import datetime
from datetime import timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs7
from cryptography.x509.oid import NameOID

# ---------------------------------------------------------------------------
# Internal helpers: key / certificate / CRL / CMS construction
# ---------------------------------------------------------------------------

def _gen_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _name(common_name: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])


def _build_ca(common_name: str) -> tuple[rsa.RSAPrivateKey, x509.Certificate]:
    key = _gen_key()
    subject = issuer = _name(common_name)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime(2025, 1, 1, tzinfo=timezone.utc))
        .not_valid_after(datetime.datetime(2030, 1, 1, tzinfo=timezone.utc))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(private_key=key, algorithm=hashes.SHA256())
    )
    return key, cert


def _build_ee(
    common_name: str,
    *,
    ca_key: rsa.RSAPrivateKey,
    ca_cert: x509.Certificate,
) -> tuple[rsa.RSAPrivateKey, x509.Certificate]:
    key = _gen_key()
    cert = (
        x509.CertificateBuilder()
        .subject_name(_name(common_name))
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime(2025, 1, 1, tzinfo=timezone.utc))
        .not_valid_after(datetime.datetime(2030, 1, 1, tzinfo=timezone.utc))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(private_key=ca_key, algorithm=hashes.SHA256())
    )
    return key, cert


def _to_b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode('ascii')


def _cert_b64(cert: x509.Certificate) -> str:
    return _to_b64(cert.public_bytes(serialization.Encoding.DER))


def _cms_b64(
    *,
    signer_key: rsa.RSAPrivateKey,
    signer_cert: x509.Certificate,
    payload: bytes,
) -> str:
    """Wrap *payload* in a DER-encoded CMS SignedData and return as base64."""
    return _to_b64(
        pkcs7.PKCS7SignatureBuilder()
        .set_data(payload)
        .add_signer(signer_cert, signer_key, hashes.SHA256())
        .sign(serialization.Encoding.DER, [pkcs7.PKCS7Options.Binary])
    )


def _crl_b64(
    *,
    issuer_key: rsa.RSAPrivateKey,
    issuer_cert: x509.Certificate,
    last_update: datetime.datetime | None = None,
    next_update: datetime.datetime,
    crl_number: int | None = None,
    revoked: list[tuple[int, datetime.datetime]] | None = None,
) -> str:
    """Build a DER-encoded CRL and return as base64."""
    if last_update is None:
        last_update = next_update - datetime.timedelta(days=1)
    builder = (
        x509.CertificateRevocationListBuilder()
        .issuer_name(issuer_cert.subject)
        .last_update(last_update)
        .next_update(next_update)
    )
    if crl_number is not None:
        builder = builder.add_extension(x509.CRLNumber(crl_number), critical=False)
    for serial, rev_date in (revoked or []):
        builder = builder.add_revoked_certificate(
            x509.RevokedCertificateBuilder()
            .serial_number(serial)
            .revocation_date(rev_date)
            .build()
        )
    return _to_b64(
        builder.sign(private_key=issuer_key, algorithm=hashes.SHA256())
        .public_bytes(serialization.Encoding.DER)
    )


# ---------------------------------------------------------------------------
# Pre-encoded RFC 6486 Manifest DER constants
#
# These were generated once with pyasn1, verified to decode correctly, and
# hardcoded to avoid schema-mutation issues in pyasn1 0.6.x when Manifest()
# is called more than once in the same process.
# ---------------------------------------------------------------------------

# manifestNumber=42, thisUpdate=20250101, nextUpdate=20300101, 2 file entries
# (corpus.roa and corpus.crl, each with a 32-byte zero hash)
_MANIFEST_VALID_DER = base64.b64decode(
    'MIGUAgEqGA8yMDI1MDEwMTAwMDAwMFoYDzIwMzAwMTAxMDAwMDAwWgYJYIZIAWUDBAIBMGIw'
    'LxYKY29ycHVzLnJvYQMhAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAMC8WCmNvcn'
    'B1cy5jcmwDIQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=='
)

# manifestNumber=1, thisUpdate=20240101, nextUpdate=20240102 (stale), 1 file entry
_MANIFEST_STALE_DER = base64.b64decode(
    'MGICAQEYDzIwMjQwMTAxMDAwMDAwWhgPMjAyNDAxMDIwMDAwMDBaBglghkgBZQMEAgEwMDAu'
    'FglzdGFsZS5yb2ADIQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=='
)

# manifestNumber=0, thisUpdate=20250101, nextUpdate=20300101, empty fileList
_MANIFEST_EMPTY_DER = base64.b64decode(
    'MDICAQAYDzIwMjUwMTAxMDAwMDAwWhgPMjAzMDAxMDEwMDAwMDBaBglghkgBZQMEAgEwAA=='
)

# ---------------------------------------------------------------------------
# Corpus key / certificate infrastructure (built once at import time)
# ---------------------------------------------------------------------------

_CA_KEY, _CA_CERT = _build_ca('RPKI Corpus CA')

_ROA_EE_KEY, _ROA_EE_CERT = _build_ee(
    'RPKI Corpus ROA EE', ca_key=_CA_KEY, ca_cert=_CA_CERT
)
_MFT_EE_KEY, _MFT_EE_CERT = _build_ee(
    'RPKI Corpus Manifest EE', ca_key=_CA_KEY, ca_cert=_CA_CERT
)
_ASPA_EE_KEY, _ASPA_EE_CERT = _build_ee(
    'RPKI Corpus ASPA EE', ca_key=_CA_KEY, ca_cert=_CA_CERT
)

# ---------------------------------------------------------------------------
# VALID corpus items
# ---------------------------------------------------------------------------

# Provenance: self-signed RSA CA certificate; BasicConstraints CA:True; 2025–2030 validity.
# Intent: exercises _load_der_certificate on a well-formed CA cert; expect subject CN present.
CORPUS_CA_CERT_VALID_B64: str = _cert_b64(_CA_CERT)

# Provenance: RSA leaf certificate signed by _CA_CERT; BasicConstraints CA:False; 2025–2030.
# Intent: exercises _load_der_certificate on a well-formed EE cert; expect issuer = CA CN.
CORPUS_EE_CERT_VALID_B64: str = _cert_b64(_ROA_EE_CERT)

# Provenance: DER CRL; last_update=2029-12-31, next_update=2030-01-01; CRLNumber=1; no revoked entries.
# Intent: exercises _parse_cms_crl_metadata; expect freshness_status='fresh', revoked_count=0.
CORPUS_CRL_FRESH_B64: str = _crl_b64(
    issuer_key=_CA_KEY,
    issuer_cert=_CA_CERT,
    next_update=datetime.datetime(2030, 1, 1, tzinfo=timezone.utc),
    crl_number=1,
)

# Provenance: DER CRL; one revoked serial (12345 revoked 2024-06-01); CRLNumber=5; next_update=2030.
# Intent: exercises _parse_cms_crl_metadata; expect revoked_count=1, crl_number='5'.
CORPUS_CRL_WITH_REVOKED_B64: str = _crl_b64(
    issuer_key=_CA_KEY,
    issuer_cert=_CA_CERT,
    next_update=datetime.datetime(2030, 1, 1, tzinfo=timezone.utc),
    crl_number=5,
    revoked=[(12345, datetime.datetime(2024, 6, 1, tzinfo=timezone.utc))],
)

# Provenance: CMS SignedData; eContent is pre-encoded RFC 6486 Manifest DER; 2 file entries; nextUpdate=2030.
# Intent: exercises _parse_cms_manifest_metadata; expect manifest_number=42, 2 file entries.
CORPUS_MANIFEST_VALID_B64: str = _cms_b64(
    signer_key=_MFT_EE_KEY,
    signer_cert=_MFT_EE_CERT,
    payload=_MANIFEST_VALID_DER,
)

# Provenance: CMS SignedData wrapping opaque payload b'corpus-roa-payload', signed by ROA EE cert.
# Intent: exercises _load_cms_signed_data and _load_cms_certificates; expect 1 embedded cert.
CORPUS_ROA_CMS_VALID_B64: str = _cms_b64(
    signer_key=_ROA_EE_KEY,
    signer_cert=_ROA_EE_CERT,
    payload=b'corpus-roa-payload',
)

# Provenance: CMS SignedData wrapping opaque payload b'corpus-aspa-payload', signed by ASPA EE cert.
# Intent: exercises _load_cms_signed_data for an ASPA-URI-typed object; expect signed data present.
CORPUS_ASPA_CMS_VALID_B64: str = _cms_b64(
    signer_key=_ASPA_EE_KEY,
    signer_cert=_ASPA_EE_CERT,
    payload=b'corpus-aspa-payload',
)

# ---------------------------------------------------------------------------
# STALE corpus items
# ---------------------------------------------------------------------------

# Provenance: DER CRL; next_update=2024-01-02 (past); no CRLNumber.
# Intent: exercises _parse_cms_crl_metadata; expect freshness_status='stale'.
CORPUS_CRL_STALE_B64: str = _crl_b64(
    issuer_key=_CA_KEY,
    issuer_cert=_CA_CERT,
    next_update=datetime.datetime(2024, 1, 2, tzinfo=timezone.utc),
)

# Provenance: CMS SignedData; eContent is pre-encoded RFC 6486 Manifest DER; nextUpdate=2024-01-02 (past).
# Intent: exercises _parse_cms_manifest_metadata; parser returns dates without error on stale input.
CORPUS_MANIFEST_STALE_B64: str = _cms_b64(
    signer_key=_MFT_EE_KEY,
    signer_cert=_MFT_EE_CERT,
    payload=_MANIFEST_STALE_DER,
)

# ---------------------------------------------------------------------------
# EDGE CASE corpus items
# ---------------------------------------------------------------------------

# Provenance: DER CRL; next_update=2030; no CRLNumber extension.
# Intent: _parse_cms_crl_metadata must return crl_number='' when extension absent.
CORPUS_CRL_NO_NUMBER_B64: str = _crl_b64(
    issuer_key=_CA_KEY,
    issuer_cert=_CA_CERT,
    next_update=datetime.datetime(2030, 1, 1, tzinfo=timezone.utc),
)

# Provenance: CMS SignedData; eContent is pre-encoded RFC 6486 Manifest DER with empty fileList.
# Intent: _parse_cms_manifest_metadata must return file_entries=[] without error.
CORPUS_MANIFEST_EMPTY_FILES_B64: str = _cms_b64(
    signer_key=_MFT_EE_KEY,
    signer_cert=_MFT_EE_CERT,
    payload=_MANIFEST_EMPTY_DER,
)

# Provenance: CMS SignedData; eContent is opaque bytes that cannot be decoded as a Manifest.
# Intent: _parse_cms_manifest_metadata must return {} when eContent is not a valid Manifest.
CORPUS_CMS_NON_MANIFEST_B64: str = _cms_b64(
    signer_key=_ROA_EE_KEY,
    signer_cert=_ROA_EE_CERT,
    payload=b'not-a-manifest-structure',
)

# ---------------------------------------------------------------------------
# MALFORMED corpus items
# ---------------------------------------------------------------------------

# Intent: all parser functions must return empty dict / None / [] — never raise.

# Empty string: common null/missing-field sentinel from Krill JSON.
CORPUS_EMPTY_STRING: str = ''

# Unpaddable base64: contains characters outside the base64 alphabet.
CORPUS_INVALID_BASE64: str = '!!!not-valid-base64!!!'

# Valid base64 of random non-DER bytes.
CORPUS_RANDOM_BYTES_B64: str = _to_b64(b'\x00\x01\x02\x03\x04\x05malformed-der')

# Valid base64 of a partial DER SEQUENCE header — triggers decoder errors.
CORPUS_TRUNCATED_DER_B64: str = _to_b64(b'\x30\x82')
