import datetime
import json
import os
import time
from typing import List, Tuple

import requests
from dateutil import parser

from booking_user import BookingUser


class BookingSystem:
    def __init__(self, users_configs: str, base_url: str):
        with open(users_configs, 'r') as j:
            contents = json.loads(j.read())
        self.booking_users = [BookingUser(base_url, user_preference) for user_preference in contents]

    def _auth_users(self) -> Tuple[int, List[BookingUser]]:
        auth_users = 0
        auth_users_list = []

        for user in self.booking_users:
            try:
                user.auth()
                user.me()
                auth_users += 1
                auth_users_list.append(user)
                print(f"Authentication success for user {user.name}")
            except requests.exceptions.HTTPError:
                print(f"Authentication failed for user {user.name}")

        return auth_users, auth_users_list

    def enforce_auth(self):
        while True:
            auth_users, auth_user_list = self._auth_users()
            if auth_users == len(self.booking_users):
                print("Successfully authenticated all the users")
                break
            elif auth_users > 0:
                print("Failed authentication for some users. Skipping those users.")
                self.booking_users = auth_user_list
                break
            else:
                print("Failed authentication for all users. Sleeping 10 mins")

            time.sleep(600)

    def search_target_date(self, dt, target_last_date: str):
        print(f"Start searching for date {target_last_date} at {dt.hour}h{dt.minute}m")
        start = time.time()
        while True:
            user = self.booking_users[0]
            last_dates_available = []

            for class_type in user.classes:
                url = os.path.join(user.base_url, user.classes_url, class_type)
                r = requests.get(url, headers=user.headers, timeout=user.timeout)
                r.raise_for_status()

                classes = r.json()
                last_date = parser.parse(classes[-1]["_id"])
                last_dates_available.append(datetime.datetime.strftime(last_date, "%Y-%m-%d"))

            dt = datetime.datetime.now()
            if target_last_date in last_dates_available:
                print(f"Found target date available at {dt.hour}h{dt.minute}m")
                break
            else:
                print(f"Target date not available at {dt.hour}h{dt.minute}m. Sleeping 21m20s.")
                end = time.time()
                if end - start >= 10800:
                    print("3 hours have passed since we started searching for the target date. Re-authenticating.")
                    self.enforce_auth()
                    start = time.time()
                time.sleep(1220)

    def save_user_bookings(self):
        bookings_to_save = {}
        for user in self.booking_users:
            scheduled_classes = user.get_scheduled_classes()
            all_bookings = {}

            for class_type, bookings in scheduled_classes.items():
                for booking in bookings:
                    class_date = booking['classDate'][0]
                    data = {"classType": class_type, "class_id": booking["class_id"],
                            "booking_id": booking["booking_id"], "classTime": booking["classTime"]}
                    if class_date in all_bookings.keys():
                        all_bookings[class_date].append(data)
                    else:
                        all_bookings[class_date] = [data]

            if len(all_bookings) > 0:
                bookings_to_save[user.name] = all_bookings

        d = datetime.datetime.now().strftime("%Y-%m-%d")
        filename = f"users_data/{d}_scheduled_classes.txt"
        with open(filename, 'w') as outfile:
            json.dump(bookings_to_save, outfile)

    def do_bookings(self):
        for user in self.booking_users:
            print("-------------------------------------------------------------------------")
            print(f"Start bookings for user {user.name}")
            candidates = user.generate_candidates()
            classes_to_schedule = user.get_classes_to_schedule(candidates)

            len_candidates = sum([len(x) for _, x in candidates.items()])
            if len(classes_to_schedule) == 0 and len_candidates > 0:
                print(f"No classes available for user {user.name} - tried to book {candidates}")
            elif len(classes_to_schedule) == 0:
                print(f"All the classes are already booked for user {user.name}")
            else:
                for class_type, classes in classes_to_schedule.items():
                    print(f"Booking class type {class_type}")
                    for class_candidate in classes:
                        day = parser.parse(class_candidate["classDate"]).strftime("%Y-%m-%d")
                        user.book_class(class_candidate["_id"])
                        print(f"{day} at {class_candidate['classTime']}")
                    print("\n")

    def run(self):
        while True:
            dt = datetime.datetime.now()
            target_last_date = dt + datetime.timedelta(days=7)
            target_last_date = datetime.datetime.strftime(target_last_date, "%Y-%m-%d")
            print(f"Start bookings for {dt.day}/{dt.month}/{dt.year}")

            self.enforce_auth()
            self.search_target_date(dt, target_last_date)
            self.do_bookings()
            self.save_user_bookings()

            dt = datetime.datetime.now()
            tomorrow = dt + datetime.timedelta(days=1)
            time_until_tomorrow = datetime.datetime.combine(tomorrow, datetime.time.min) - dt
            seconds = time_until_tomorrow.seconds + 60
            hours = seconds // 3600
            minutes = (seconds // 60) % 60
            print(f"Success in bookings at {dt.hour}h{dt.minute}m, sleeping {hours}h{minutes}m until tomorrow")
            time.sleep(seconds)
