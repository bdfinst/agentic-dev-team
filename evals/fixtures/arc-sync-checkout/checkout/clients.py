"""HTTP clients for downstream services. Each call raises on timeout or 5xx."""


class _Client:
    def __init__(self, base_url):
        self.base_url = base_url


class Inventory(_Client):
    def reserve(self, items, timeout):
        ...


class Pricing(_Client):
    def quote(self, items, tier, timeout):
        ...


class Notify(_Client):
    def send_confirmation_email(self, email, order_id, timeout):
        ...


inventory = Inventory("https://inventory.internal.example.com")
pricing = Pricing("https://pricing.internal.example.com")
notify = Notify("https://notify.internal.example.com")
