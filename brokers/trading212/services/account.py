class AccountService:

    def __init__(self, client):
        self.client = client

    def get_cash(self):
        return self.client.get("/equity/account/cash")

    def get_portfolio(self):
        return self.client.get("/equity/portfolio")
