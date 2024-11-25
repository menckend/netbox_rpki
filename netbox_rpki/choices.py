from utilities.choices import ChoiceSet


class CertificateStatusChoices(ChoiceSet):
    key = "Certificate.status"

    STATUS_VALID = 'valid'
    STATUS_PLANNED = 'planned'
    STATUS_REVOKED = 'revoked'

    CHOICES = [
        (STATUS_VALID, 'valid', 'blue'),
        (STATUS_PLANNED, 'planned', 'cyan'),
        (STATUS_REVOKED, 'revoked', 'red'),
    ]
