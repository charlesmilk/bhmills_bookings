import datetime
import os
from typing import Dict, List, Any, Tuple, Union

import requests
from dateutil import parser


class BookingUser:
    def __init__(self, base_url, user_info):
        self.base_url = base_url
        self.name = user_info["name"]
        self.user_email = user_info["email"]
        self.password = user_info["password"]
        self.user_preferences = user_info["preferences"]
        self.auth_url = "auth/local"
        self.classes_url = "api/class/gym/5fd7cff72eb93d371e0aa7de"
        self.headers = {"Content-Type": "application/json"}
        self.timeout = 3.0
        self.user_id = None
        self.classes = ["swimmingClass", "gymClass", "tennisClass"]

    def get_scheduled_classes(self) -> Dict[str, List[Dict[str, Any]]]:
        # return scheduled classes for a given user
        booked_classes = {key_class: [] for key_class in self.classes}

        for class_type in booked_classes.keys():
            url = os.path.join(self.base_url, f"api/users/{class_type}/upcoming")
            r = requests.get(url, headers=self.headers, timeout=self.timeout)
            r.raise_for_status()

            for booked_class in r.json():
                if booked_class["status"] == "active":
                    class_tmp = dict()
                    class_tmp["booking_id"] = booked_class["_id"]
                    booked_class = booked_class['class']
                    class_tmp["class_id"] = booked_class["_id"]
                    day = parser.parse(booked_class["classDate"])
                    class_tmp["classDate"] = (day.strftime("%Y-%m-%d"), day.strftime("%A"))
                    class_tmp["classTime"] = booked_class["classTime"]
                    booked_classes[class_type].append(class_tmp)

        return booked_classes

    def generate_candidates(self) -> Dict[str, List[Tuple[Union[str, List[str]]]]]:
        # returns the classes that the user wants to book: has preference AND it is not in its list of scheduled class
        ndays = 8
        candidate_days = self._generate_candidate_days(ndays)
        scheduled_classes = self.get_scheduled_classes()
        candidates = self._filter_days_to_schedule(candidate_days, scheduled_classes)

        candidates_filter = {}
        for class_type, class_data in candidates.items():
            if len(class_data) > 0:
                candidates_filter[class_type] = class_data

        return candidates_filter

    def get_classes_to_schedule(self, candidates: Dict[str, List[Tuple[Union[str, List[str]]]]]) -> Dict[
        str, List[Dict[str, Any]]]:
        # receives the candidates already filtered by the user preferences and filtered by what we already scheduled
        # it then searches for availability for those candidates, if found returns that class information
        global_classes_to_schedule = {}
        for class_type, candidates_class in candidates.items():
            candidates_class = candidates[class_type]
            url = os.path.join(self.base_url, self.classes_url, class_type)
            r = requests.get(url, headers=self.headers, timeout=self.timeout)
            r.raise_for_status()

            bookings = r.json()
            days_to_filter = [d[0] for d in candidates_class]

            filtered_bookings = {}
            classes_to_schedule = []
            for b in bookings:
                d = parser.parse(b["_id"]).strftime("%Y-%m-%d")
                if d in days_to_filter:
                    filtered_bookings[d] = b

            for candidate in candidates_class:
                day = candidate[0]
                candidate_time = self._parse_hour(candidate[2])
                required_spots = 1 + len(candidate[3])

                for real_class in filtered_bookings[day]["classes"]:
                    available_spots = real_class["limit"] - real_class["joinedUsers"]
                    real_class_time = self._parse_hour(real_class["classTime"])
                    if real_class_time == candidate_time and available_spots >= required_spots and real_class["active"]:
                        real_class["classDate"] = parser.parse(real_class["classDate"]).strftime("%Y-%m-%d")
                        classes_to_schedule.append(real_class)

            if len(classes_to_schedule) > 0:
                global_classes_to_schedule[class_type] = classes_to_schedule

        return global_classes_to_schedule

    def get_not_available_classes(self, candidates: Dict[str, List[Tuple[Union[str, List[str]]]]],
                                  classes_to_schedule: Dict[str, List[Dict[str, Any]]]):
        available_dates = {class_type: [] for class_type, _ in classes_to_schedule.items()}
        for class_type, classes_data in classes_to_schedule.items():
            for real_class in classes_data:
                available_dates[class_type].append(real_class["classDate"])

        not_available_classes = {}
        for class_type, class_data in candidates.items():
            if len(class_data) > 0:
                if class_type in available_dates.keys():
                    classes_not_in = []
                    for class_tuple in class_data:
                        if class_tuple[0] not in available_dates[class_type]:
                            classes_not_in.append(class_tuple)
                    if len(classes_not_in) > 0:
                        not_available_classes[class_type] = classes_not_in
                else:
                    not_available_classes[class_type] = class_data

        return not_available_classes

    def book_class(self, class_id: str):
        url = os.path.join(self.base_url, "api/class", class_id)
        data = f'{{"userId":"{self.user_id}","isSinglePayment":true}}'
        r = requests.post(url, headers=self.headers, data=data, timeout=self.timeout)
        r.raise_for_status()

    def cancel_class(self, booking_id: str):
        url = os.path.join(self.base_url, "api/attendance", booking_id, "cancel")
        data = f'{{"userId":"{self.user_id}"}}'
        r = requests.patch(url, headers=self.headers, data=data, timeout=self.timeout)
        r.raise_for_status()

    @staticmethod
    def _generate_candidate_days(ndays: int) -> Dict[str, List[str]]:
        # return dict of weekday: [str_date] based on ndays
        candidate_days = {}
        now = datetime.datetime.now()
        for i in range(ndays):
            day = now + datetime.timedelta(i)
            weekday = day.strftime("%A")
            if weekday in candidate_days:
                candidate_days[weekday].append(day.strftime("%Y-%m-%d"))
            else:
                candidate_days[weekday] = [day.strftime("%Y-%m-%d")]

        return candidate_days

    def _filter_days_to_schedule(self, candidate_days: Dict[str, List[str]],
                                 scheduled_classes: Dict[str, List[Dict[str, Any]]]) -> Dict[
        str, List[Tuple[Union[str, List[str]]]]]:
        # filter days for each class regarding user preferences and classes already scheduled
        class_candidates = {key: [] for key in self.user_preferences.keys()}
        now = datetime.datetime.now()
        for preference_class, preferences in self.user_preferences.items():
            for day_p in preferences:
                if day_p[0] in candidate_days.keys():
                    class_dates = candidate_days[day_p[0]]
                    class_hours = day_p[1]
                    candidate = [(class_date, day_p[0], hour, day_p[2])
                                 for hour in class_hours for class_date in class_dates]
                    class_candidates[preference_class].extend(candidate)

        # after filtering candidates using the preferences, filter the ones already scheduled
        filtered_candidates = {key: [] for key in class_candidates.keys()}
        for preference_class, preferences in class_candidates.items():
            scheduled_days = {(day["classDate"][0], day["classTime"].lower()) for day in
                              scheduled_classes[preference_class]}
            for candidate in preferences:
                candidate_date = candidate[0]
                candidate_weekday = candidate[1]
                candidate_hour = candidate[2]
                candidate_friends = candidate[3]
                preference_datetime = parser.parse(candidate_date) + self._parse_hour(candidate_hour)

                if now < preference_datetime and (candidate_date, candidate_hour) not in scheduled_days:
                    filtered_candidates[preference_class].append((candidate_date, candidate_weekday,
                                                                  candidate_hour, candidate_friends))

        return filtered_candidates

    def me(self):
        url = os.path.join(self.base_url, "api/users/me")
        r = requests.get(url, headers=self.headers, timeout=self.timeout)
        r.raise_for_status()
        response = r.json()
        self.user_id = response["_id"]

    def auth(self):
        url = os.path.join(self.base_url, self.auth_url)
        data = f'{{"email":"{self.user_email}","password":"{self.password}"}}'
        r = requests.post(url, headers=self.headers, data=data, timeout=self.timeout)
        r.raise_for_status()
        response = r.json()
        self.headers["Authorization"] = f"Bearer {response['token']}"

    def _parse_hour(self, hour_minutes: str):
        hour = hour_minutes.split()
        hour_int = int(hour[0].split(":")[0])
        minutes_int = int(hour[0].split(":")[1])

        time_of_day = hour[1].lower()
        if time_of_day == 'pm':
            hour_int = hour_int + 12

        return datetime.timedelta(hours=hour_int, minutes=minutes_int)
