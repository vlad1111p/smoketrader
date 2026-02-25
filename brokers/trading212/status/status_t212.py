from brokers.trading212.client import Trading212Client
from brokers.trading212.services.account import AccountService
from brokers.trading212.services.orders import OrdersService


def main():
    with Trading212Client() as client:
        account = AccountService(client)
        orders_service = OrdersService(client)

        cash = account.get_cash()
        portfolio = account.get_portfolio()
        open_orders = orders_service.get_orders()

        print("\nCASH:", cash)
        print("\nPORTFOLIO items:", portfolio)
        print("\nORDERS items:", open_orders)


if __name__ == "__main__":
    main()
