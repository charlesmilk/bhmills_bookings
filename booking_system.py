import argparse
import datetime
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import List, Dict, Any

import requests
from dateutil import parser

from booking_user import BookingUser

website_base_url = "https://bhmbackend.m8north.co.uk/"
offsets = {
    'gymClass': 55,
    'swimmingClass': 55,
    'tennisClass': 835
}

def init_logger(name, filename):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    fh = logging.FileHandler(filename, mode='a')
    fh.setLevel(logging.INFO)

    formatter = logging.Formatter('[%(asctime)s] %(levelname)s  %(message)s', datefmt="%Y-%m-%d %H:%M:%S")
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    return logger


class BookingSystem:
    def __init__(self, base_url: str, class_type: str, user_info, logger):
        self.base_url = base_url
        self.user = BookingUser(base_url, class_type, user_info, logger)
        self.logger = logger

    def enforce_auth(self):
        while True:
            try:
                self.user.auth()
                self.user.me()
                self.logger.info(f"Authentication success")
                break
            except requests.exceptions.HTTPError:
                self.logger.error(f"Authentication failed for user {self.user.name}. Sleeping 30 mins")
                time.sleep(1800)

    def search_target_date(self, target_last_date: str):
        self.logger.info(f"Start searching for date {target_last_date}")
        start = time.time()

        while True:
            try:
                last_dates_available = []
                url = os.path.join(self.base_url, self.user.classes_url, self.user.class_type)
                r = requests.get(url, headers=self.user.headers, timeout=self.user.timeout)
                r.raise_for_status()

                classes = r.json()
                last_date = parser.parse(classes[-1]["_id"])
                last_dates_available.append(datetime.datetime.strftime(last_date, "%Y-%m-%d"))

                dt = datetime.datetime.now()
                if target_last_date in last_dates_available:
                    self.logger.info("Found target date")
                    break
                else:
                    next_time = datetime.datetime.combine(dt, datetime.time(hour=dt.hour + 1))
                    diff = (next_time - dt)
                    secs = diff.total_seconds()
                    self.logger.info(f"Target date not available. Sleeping {secs} seconds.")

                    end = time.time()
                    if end - start >= 10800:
                        self.logger.info("Re-auth: 3 hours have passed since we started searching for the target date")
                        self.enforce_auth()
                        start = time.time()
                    time.sleep(secs)
            except requests.exceptions.HTTPError:
                self.logger.error("Connection error searching for date. Sleeping 30min.")
                time.sleep(1800)
                self.enforce_auth()

    def do_bookings(self, classes_to_schedule: List[Dict[str, Any]]):
        for class_candidate in classes_to_schedule:
            day = parser.parse(class_candidate["classDate"]).strftime("%Y-%m-%d")
            self.user.book_class(class_candidate["_id"])
            self.logger.info(f"Booked class for {day} at {class_candidate['classTime']}")

    def crawler(self, candidates, tomorrow):
        dt = datetime.datetime.now()
        start_logging = time.time()
        self.logger.info(f"There are candidates not available: {candidates}")
        self.logger.info("Crawler started")

        while dt < tomorrow and len(candidates) > 0:
            try:
                classes_to_schedule, candidates = self.user.get_classes_to_schedule(candidates)
                if len(classes_to_schedule) > 0:
                    self.do_bookings(classes_to_schedule)

                end_logging = time.time()
                if (end_logging - start_logging) // 3600 > 0:
                    self.logger.info(f"After 1h there are still classes not found. Continue searching for {candidates}")
                    start_logging = time.time()

                time.sleep(30)
                dt = datetime.datetime.now()
            except requests.exceptions.ConnectionError:
                self.logger.error("Time out detected, sleeping 10 minutes")
                time.sleep(600)
                self.enforce_auth()
                continue

        self.logger.info("Stopping crawler")

    def run(self, offset_tomorrow: int):
            while True:
                try:
                    dt = datetime.datetime.now()
                    tomorrow = datetime.datetime.combine(dt + datetime.timedelta(days=1), datetime.time.min)
                    tomorrow = tomorrow + datetime.timedelta(minutes=offset_tomorrow)
                    target_last_date = dt + datetime.timedelta(days=7)
                    target_last_date = datetime.datetime.strftime(target_last_date, "%Y-%m-%d")

                    self.enforce_auth()
                    candidates = self.user.generate_candidates()
                    self.search_target_date(target_last_date)
                    classes_to_schedule, candidates_not_available = self.user.get_classes_to_schedule(candidates)

                    if len(classes_to_schedule) > 0:
                        self.do_bookings(classes_to_schedule)
                    if len(candidates_not_available) > 0:
                        self.crawler(candidates_not_available, tomorrow)

                    dt = datetime.datetime.now()
                    if dt < tomorrow:
                        time_until_tomorrow = tomorrow - dt
                        self.logger.info(
                            f"There are no candidates to book - sleep {time_until_tomorrow} until next day")
                        time.sleep(time_until_tomorrow.seconds)
                except Exception as e:
                    self.logger.exception(e)
                    time.sleep(600)
                    continue

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument("--config", type=str)
    args = p.parse_args()

    config_path = args.config
    with open(config_path, 'r') as j:
        contents = json.loads(j.read())

    for user_data in contents:
        for class_type, class_data in user_data["preferences"].items():
            logs_path = f"users_data/logs"
            Path(logs_path).mkdir(parents=True, exist_ok=True)
            logger_name = f"{user_data['name']}_{class_type}"
            filename_log = f"{logs_path}/{logger_name}.log"
            logger = init_logger(logger_name, filename_log)

            booking_system = BookingSystem(website_base_url, class_type, user_data, logger)
            process = threading.Thread(target=booking_system.run, args=(offsets[class_type],))
            process.start()
