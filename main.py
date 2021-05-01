from booking_system import BookingSystem
import argparse

website_base_url = "https://bhmbackend.m8north.co.uk/"

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str)
    args = parser.parse_args()

    config_path = args.config
    booking_system = BookingSystem(config_path, website_base_url)
    booking_system.run()
