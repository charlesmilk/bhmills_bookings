import datetime
import os
from typing import Dict, List, Any, Tuple, Union

import requests
from dateutil import parser


class BookingUser:
    def __init__(self, base_url: str, class_type: str, user_info, logger):
        self.base_url = base_url
        self.class_type = class_type
        self.name = user_info["name"]
        self.user_email = user_info["email"]
        self.password = user_info["password"]
        self.user_preferences = user_info["preferences"][self.class_type]
        self.auth_url = "auth/local"
        self.classes_url = "api/class/gym/5fd7cff72eb93d371e0aa7de"
        self.headers = {"Content-Type": "application/json"}
        self.timeout = 3.0
        self.user_id = None
        self.logger = logger

    def get_scheduled_classes(self) -> List[Dict[str, Any]]:
        # return scheduled classes for a given user
        booked_classes = []
        url = os.path.join(self.base_url, f"api/users/{self.class_type}/upcoming")
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
                booked_classes.append(class_tmp)

        return booked_classes

    def generate_candidates(self) -> List[Tuple[Union[str, List[str]]]]:
        # returns the classes that the user wants to book: has preference AND it is not in its list of scheduled class
        ndays = 8
        candidate_days = self._generate_candidate_days(ndays)
        scheduled_classes = self.get_scheduled_classes()
        candidates = self._filter_days_to_schedule(candidate_days, scheduled_classes)

        return candidates

    def get_classes_to_schedule(self, candidates_class: List[Tuple[Union[str, List[str]]]]) -> Tuple[
                                List[Dict[str, Any]], List[Tuple[Union[str, List[str]]]]]:
        # receives the candidates already filtered by the user preferences and filtered by what we already scheduled
        # it then searches for availability for those candidates, if found returns that class information
        url = os.path.join(self.base_url, self.classes_url, self.class_type)
        r = requests.get(url, headers=self.headers, timeout=self.timeout)
        r.raise_for_status()
        bookings = r.json()

        days_to_filter = [d[0] for d in candidates_class]
        filtered_bookings = {}
        classes_to_schedule = []
        candidates_scheduled = []
        for b in bookings:
            d = parser.parse(b["_id"]).strftime("%Y-%m-%d")
            if d in days_to_filter:
                filtered_bookings[d] = b

        for candidate in candidates_class:
            day = candidate[0]
            candidate_time = self._parse_hour(candidate[2])
            required_spots = 1 + len(candidate[3])

            if day in filtered_bookings.keys():
                for real_class in filtered_bookings[day]["classes"]:
                    available_spots = real_class["limit"] - real_class["joinedUsers"]
                    real_class_time = self._parse_hour(real_class["classTime"])
                    if real_class_time > candidate_time:
                        break

                    if real_class_time == candidate_time:
                        cancel = False
                        for attendance in real_class["attendanceList"]:
                            if attendance["user"] == self.user_id and attendance["status"] == "cancelled":
                                self.logger.info(
                                    f"The {self.class_type} for {day} at {candidate[2]} "
                                    f"was cancelled by user - remove from scheduling")
                                cancel = True
                                candidates_scheduled.append(candidate)
                                break
                        if not cancel and available_spots >= required_spots and real_class["active"]:
                            real_class["classDate"] = parser.parse(real_class["classDate"]).strftime("%Y-%m-%d")
                            classes_to_schedule.append(real_class)
                            candidates_scheduled.append(candidate)

        candidates_not_available = [c for c in candidates_class if c not in candidates_scheduled]
        return classes_to_schedule, candidates_not_available

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
                                 scheduled_classes: List[Dict[str, Any]]) -> List[Tuple[Union[str, List[str]]]]:
        # filter days for each class regarding user preferences and classes already scheduled
        class_candidates = []
        now = datetime.datetime.now()

        for day_p in self.user_preferences:
            if day_p[0] in candidate_days.keys():
                class_dates = candidate_days[day_p[0]]
                class_hours = day_p[1]
                candidate = [(class_date, day_p[0], hour, day_p[2])
                             for hour in class_hours for class_date in class_dates]
                class_candidates.extend(candidate)

        # after filtering candidates using the preferences, filter the ones already scheduled
        filtered_candidates = []
        for candidate in class_candidates:
            scheduled_days = {(day["classDate"][0], day["classTime"].lower()) for day in
                              scheduled_classes}
            candidate_date = candidate[0]
            candidate_hour = candidate[2]
            preference_datetime = parser.parse(candidate_date) + self._parse_hour(candidate_hour)

            if now < preference_datetime and (candidate_date, candidate_hour) not in scheduled_days:
                filtered_candidates.append(candidate)

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

    @staticmethod
    def _parse_hour(hour_minutes: str):
        hour = hour_minutes.split()
        hour_int = int(hour[0].split(":")[0])
        minutes_int = int(hour[0].split(":")[1])

        time_of_day = hour[1].lower()
        if time_of_day == 'pm' and hour_int < 12:
            hour_int = hour_int + 12

        return datetime.timedelta(hours=hour_int, minutes=minutes_int)
