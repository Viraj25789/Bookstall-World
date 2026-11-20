import unittest

from werkzeug.security import check_password_hash

from app import app
from extensions import db
from models import CartItem, Product, User
from utils import setup_store


class BookstallTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config.update(
            TESTING=True,
            SECRET_KEY="test-secret-key",
        )
        with app.app_context():
            db.create_all()

    def setUp(self):
        with app.app_context():
            db.drop_all()
            db.create_all()

    def tearDown(self):
        with app.app_context():
            db.session.remove()
            db.drop_all()

    def test_setup_store_creates_only_configured_admin(self):
        with app.app_context():
            setup_store("a-strong-test-password")
            admin = User.query.filter_by(username="admin").one()
            self.assertEqual(admin.role, "admin")
            self.assertTrue(check_password_hash(admin.password, "a-strong-test-password"))
            self.assertIsNone(User.query.filter_by(username="alice").first())

    def test_setup_store_rejects_short_password(self):
        with app.app_context():
            with self.assertRaises(ValueError):
                setup_store("short")

    def test_customer_cannot_remove_another_users_cart_item(self):
        with app.app_context():
            owner = User(username="owner", password="hash", role="customer")
            other = User(username="other", password="hash", role="customer")
            product = Product(name="Python Book", category="Education", price=20, stock_quantity=5)
            db.session.add_all([owner, other, product])
            db.session.flush()
            cart_item = CartItem(user_id=owner.id, product_id=product.id, quantity=1)
            db.session.add(cart_item)
            db.session.commit()
            cart_item_id = cart_item.id
            other_id = other.id

        client = app.test_client()
        with client.session_transaction() as session:
            session.update(user_id=other_id, username="other", role="customer")
        response = client.post(f"/remove_from_cart/{cart_item_id}")
        self.assertEqual(response.status_code, 404)

        with app.app_context():
            self.assertIsNotNone(db.session.get(CartItem, cart_item_id))


if __name__ == "__main__":
    unittest.main()
