import unittest
from unittest.mock import patch
from kafka_producer import send_to_kafka

class TestKafkaProducer(unittest.TestCase):

    @patch('builtins.print') # Mock print to check output
    def test_send_to_kafka_simulated_success(self, mock_print):
        topic = "test_topic"
        data = {"message": "hello kafka"}

        result = send_to_kafka(topic, data)

        self.assertTrue(result)
        # Check if the simulation print statement was called correctly
        mock_print.assert_any_call(f"Simulating sending data to Kafka topic '{topic}': {data}")

    # In a real scenario, you would test actual Kafka interactions or mock the Kafka client library
    # For example, if using kafka-python:
    # @patch('kafka.KafkaProducer.send')
    # @patch('kafka.KafkaProducer.flush')
    # def test_send_to_kafka_real_client(self, mock_flush, mock_send):
    #     # Setup KafkaProducer instance mock if send_to_kafka instantiates it
    #     # ...
    #     topic = "real_topic"
    #     data = {"message": "real data"}
    #
    #     # Assuming send_to_kafka creates and uses a KafkaProducer instance
    #     # This part depends on how kafka_producer.py is structured
    #     # For now, the function is standalone and doesn't use a class.
    #
    #     # If send_to_kafka was:
    #     # from kafka import KafkaProducer
    #     # producer = KafkaProducer(bootstrap_servers='localhost:9092')
    #     # producer.send(topic, value=data)
    #     # producer.flush()
    #
    #     # Then the test would be more involved.
    #     # For the current simple simulation, the test above is sufficient.
    #     pass

if __name__ == "__main__":
    unittest.main()
