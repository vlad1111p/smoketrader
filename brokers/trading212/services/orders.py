from brokers.trading212.client import Trading212Client
from brokers.trading212.services.instruments import InstrumentsService


class OrdersService:

    def __init__(self, client):
        self.client = client

    def get_orders(self):
        return self.client.get("/equity/orders")

    def place_market_order(self, ticker: str, quantity: float):
        payload = {
            "ticker": ticker,
            "quantity": quantity
        }
        return self.client.post("/equity/orders/market", json=payload)

    def cancel_order(self, order_id: str):
        return self.client.delete(f"/equity/orders/{order_id}")


def main():
    print("Running OrdersService value-based test...\n")

    with Trading212Client() as client:
        orders_service = OrdersService(client)
        instruments = InstrumentsService(client)
        print(orders_service.get_orders())

        instrument_id = instruments.find_by_short_name("AAPL")["ticker"]

        print("Placing BUY order of quantity 0.1... for " + instrument_id)
        buy_order = orders_service.place_market_order(
            ticker=instrument_id,
            quantity=0.1
        )
        print("BUY RESPONSE:", buy_order)


if __name__ == "__main__":
    main()
