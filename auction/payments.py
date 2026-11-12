class DisabledPaymentAdapter:
    """No provider credentials or redirect-based verification in the pilot."""
    enabled = False

    def create_invoice(self, *args, **kwargs):
        raise RuntimeError('Live payment providers are disabled. Pay the seller only in a future approved pilot.')

    def verify_payment(self, *args, **kwargs):
        raise RuntimeError('No provider verification is configured.')
