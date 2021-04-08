from booking_system import BookingSystem

website_base_url = "https://bhmbackend.m8north.co.uk/"
path_users_data = "users_data/users_info.json"

if __name__ == '__main__':
    booking_system = BookingSystem(path_users_data, website_base_url)
    booking_system.run()
