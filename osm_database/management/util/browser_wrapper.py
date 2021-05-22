import os
import pathlib
import pickle
import sys
import time
from distutils import util as distutils_util

import requests
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.support.expected_conditions import staleness_of
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec

from osm_database.management.commands.util import send_notification
from root.utils import send_capcha_email

current_dir = os.path.dirname(os.path.abspath(__file__))


drivers_executables = {
    webdriver.Chrome: os.path.join(current_dir, 'browser-drivers', 'chromedriver'),
    webdriver.PhantomJS: os.path.join(current_dir, 'browser-drivers', 'phantomjs'),
}


class ReloadRequiredException(Exception):
    def __init__(self):
        super(ReloadRequiredException, self).__init__()


class CaptchaUnsolvableException(Exception):
    def __init__(self):
        super(CaptchaUnsolvableException, self).__init__()


class CaptchaSolver:
    def __init__(self, browser, pageurl, google_abuse_exemption_cookie=None):
        self.browser = browser
        self.api_key = '2bd505f9784c9de73e6f74c1fff4fe29'
        self.pageurl = pageurl
        self.site_key = None
        self.request_id = None
        self.google_abuse_exemption_cookie = google_abuse_exemption_cookie

    def run(self):
        self._get_site_key()
        self._submit_2captcha()
        return self._retrieve_captcha_response()

    def _get_site_key(self):
        g_recaptcha_element = self.browser.find_element_by_css_selector('.g-recaptcha')
        self.site_key = g_recaptcha_element.get_attribute('data-sitekey')
        self.data_s = g_recaptcha_element.get_attribute('data-s')

    def _submit_2captcha(self):
        form = {"method": "userrecaptcha",
                "googlekey": self.site_key,
                "data-s": self.data_s,
                "key": self.api_key,
                "pageurl": self.pageurl,
                "useragent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36",
                "json": 1}

        if self.google_abuse_exemption_cookie is not None:
            cookies_str = ";".join(['{}:{}'.format(k, v) for k, v in self.google_abuse_exemption_cookie.items()])
            form['cookies'] = cookies_str

        print('Submitting request for captcha solver: {}'.format(form))

        response = requests.post('http://2captcha.com/in.php', data=form)
        response_json = response.json()
        error_text = response_json.get('error_text', '')
        if error_text != '':
            send_notification('Google Querier', '2Captcha unsuccessful. Message: {}'.format(error_text))
            print(form, file=sys.stderr)
            raise Exception('Query unsuccessful: {}'.format(error_text))
        self.request_id = response_json['request']
        print('Request ID = {}'.format(self.request_id))

    def _retrieve_captcha_response(self):
        url = f"http://2captcha.com/res.php?key={self.api_key}&action=get&id={self.request_id}&json=1"
        captcha_solved_successful = False
        res_json = None
        while not captcha_solved_successful:
            try:
                res = requests.get(url)
                res_json = res.json()
                response_status = res_json['status']
                if response_status == 0:
                    response = res_json['request']
                    if response == 'ERROR_CAPTCHA_UNSOLVABLE':
                        raise CaptchaUnsolvableException()
                    else:
                        time.sleep(3)
                else:
                    response_id = res_json['request']
                    print(f'Get response: {response_id}')
                    populate_response_js = f'document.getElementById("g-recaptcha-response").innerHTML="{response_id}";'
                    self.browser.execute_script(populate_response_js)
                    self.browser.find_element_by_id('captcha-form').submit()
                    # self.browser.find_element_by_id("recaptcha-demo-submit").submit()
                    captcha_solved_successful = True
                    print('Response populated, please submit form')
            except CaptchaUnsolvableException:
                raise
            except Exception:
                raise ReloadRequiredException()

        bypass_token = res_json.get('cookies', None)
        return bypass_token


class BrowserWrapper:
    def __init__(self, cache_dir, cookies=None):
        self.driver = None
        self.browser = None
        self.cookies = None
        self.google_abuse_exemption_cookie = None

        self.cache_dir = cache_dir
        pathlib.Path(cache_dir).mkdir(parents=True, exist_ok=True)

        # self.cookies_cache_file = os.path.join(self.cache_dir, 'cookies.pkl')
        self.first_time = True
        self.browser_initiated = False
        self.auto_solve_captcha = False
        self.cookies = cookies

    def init_browser(self):
        options = webdriver.ChromeOptions()
        chrome_prefs = {}
        options.experimental_options["prefs"] = chrome_prefs
        chrome_prefs["profile.default_content_settings"] = {"images": 2}
        chrome_prefs["profile.managed_default_content_settings"] = {"images": 2}

        self.driver = webdriver.Chrome
        self.browser = self.driver(executable_path=drivers_executables[self.driver], chrome_options=options)
        self.browser.set_window_size(1200, 900)

        if self.first_time:
            self.first_time = False
            self.browser_initiated = True
            return

        self.browser_initiated = True

    def reload(self):
        self.browser.quit()
        self.init_browser()

    def make_query_retrial_if_fail(self, url):
        if not self.browser_initiated:
            self.init_browser()

        query_successful = False
        response = None
        retrials = 0
        while not query_successful:
            try:
                if retrials >= 0:
                    if retrials >= 3:
                        retrials = 0
                        send_notification('Googler querier', 'Max retrial exceeded')
                        raise Exception('Max retrial exceeded')
                    else:
                        response, bypass_token, cookies = self.make_query(url)
                        query_successful = True
            except CaptchaUnsolvableException as e:
                self.reload()
            except ReloadRequiredException as e:
                self.reload()
            except:
                raise

        return response

    def make_query(self, url):
        self.browser.get(url=url)
        cookies = None
        bypass_token = None

        try:
            captcha = self.browser.find_element_by_css_selector('iframe[role=presentation]')
        except NoSuchElementException:
            captcha = None

        if captcha is not None:
            if self.auto_solve_captcha:
                send_notification('Google querier', 'Attempting to solve captcha')
                print('Attempting to solve captcha')
                old_page = self.browser.find_element_by_tag_name('html')
                wait = WebDriverWait(self.browser, 1200)
                try:
                    captcha_solver = CaptchaSolver(self.browser, self.browser.current_url, self.google_abuse_exemption_cookie)
                    bypass_token = captcha_solver.run()
                    wait.until(staleness_of(old_page))
                except CaptchaUnsolvableException as e:
                    send_notification('Google querier', 'Captcha is unsolvable. Page will reload with a new captcha')
                    print('Captcha is unsolvable. Page will reload with a new captcha')
                    raise e
                except TimeoutException:
                    send_notification('Google querier', 'Failed to solve captcha in the expected time')
                    print('Failed to solve captcha in the expected time')
                    raise ReloadRequiredException()
                else:
                    send_notification('Google querier', 'Captcha solved successfully, proceeding')
                    print('Captcha solved successfully, proceeding')
            else:
                send_notification('Google querier', 'Please solve the captcha now')
                print('\nPlease solve the captcha now')

            wait = WebDriverWait(self.browser, 10)
            try:
                wait.until(ec.presence_of_element_located(('css selector', 'input.gLFyf.gsfi')))
            except TimeoutException:
                url = self.browser.current_url
                if 'www.google.com/sorry' in url:
                    send_notification('Google querier', 'Failed to solve captcha in the expected time')
                    print('\nFailed to solve captcha in the expected time')
                    raise ReloadRequiredException()
            else:
                cookies = self.browser.get_cookies()

        return self.browser.page_source, bypass_token, cookies