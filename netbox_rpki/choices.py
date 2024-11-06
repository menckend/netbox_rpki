from utilities.choices import ChoiceSet


class CertificateStatusChoices(ChoiceSet):
    key = "Certificate.status"

    STATUS_VALID = 'valid'
    STATUS_PLANNED = 'planned'
    STATUS_REVOKED = 'revoked'

    CHOICES = [
        (STATUS_ACTIVE, 'Active', 'blue'),
        (STATUS_RESERVED, 'Reserved', 'cyan'),
        (STATUS_DEPRECATED, 'Deprecated', 'red'),
    ]

