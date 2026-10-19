"""Browser automation tests for the CodeLiteracy frontend using Selenium WebDriver.

Run (start.bat must be running so the app is at http://localhost:5173):
    pip install selenium pytest pytest-html
    pytest test_codeliteracy_ui.py -v --html=selenium_report.html --self-contained-html
Screenshots of each test's final screen are saved in the screenshots folder.
"""
import os
from pathlib import Path

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

BASE_URL = os.environ.get("CL_URL", "http://localhost:5173")
SHOTS = Path(__file__).parent / "screenshots"
SHOTS.mkdir(exist_ok=True)
SIGN_IN_BTN = (By.XPATH, "//button[contains(., 'Sign In / Demo')]")


@pytest.fixture
def driver(request):
    options = webdriver.ChromeOptions()
    options.add_argument("--window-size=1280,900")
    if os.environ.get("HEADLESS", "0") == "1":
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
    if os.environ.get("CHROME_BINARY"):
        options.binary_location = os.environ["CHROME_BINARY"]
    service = Service(os.environ["CHROMEDRIVER"]) if os.environ.get("CHROMEDRIVER") else Service()
    drv = webdriver.Chrome(service=service, options=options)  # Selenium Manager finds the driver
    drv.get(BASE_URL)
    drv.execute_script("localStorage.clear()")  # start every test signed out
    drv.get(BASE_URL)
    yield drv
    drv.save_screenshot(str(SHOTS / f"{request.node.name}.png"))
    drv.quit()


def wait(drv, seconds=10):
    return WebDriverWait(drv, seconds)


def test_tc1_home_page_title_and_brand(driver):
    assert driver.title == "CodeLiteracy"
    brand = wait(driver).until(EC.visibility_of_element_located((By.CSS_SELECTOR, ".navbar-brand h1")))
    assert brand.text == "CodeLiteracy"
    hero = driver.find_element(By.CSS_SELECTOR, ".connect-hero h2")
    assert "Understand Any Codebase" in hero.text


def test_tc2_sample_projects_are_listed(driver):
    wait(driver).until(EC.visibility_of_element_located((By.CSS_SELECTOR, ".sample-card")))
    names = [e.text for e in driver.find_elements(By.CSS_SELECTOR, ".sample-card strong")]
    assert len(names) >= 2
    assert "nanoGPT" in names


def test_tc3_connect_button_needs_input(driver):
    box = wait(driver).until(EC.visibility_of_element_located(
        (By.CSS_SELECTOR, "input[aria-label='Repository URL or folder path']")))
    button = driver.find_element(By.CSS_SELECTOR, "form.input-group button[type='submit']")
    assert not button.is_enabled(), "Connect button should be disabled when the box is empty"
    box.send_keys("https://github.com/psf/requests")
    assert button.is_enabled(), "Connect button should be enabled after typing a URL"


def test_tc4_guest_sign_in_and_logout(driver):
    wait(driver).until(EC.element_to_be_clickable(SIGN_IN_BTN)).click()
    heading = wait(driver).until(EC.visibility_of_element_located((By.CSS_SELECTOR, ".modal-header h3")))
    assert heading.text == "Sign In to CodeLiteracy"
    driver.find_element(By.XPATH, "//button[contains(., 'Guest Demo')]").click()
    badge = wait(driver).until(EC.visibility_of_element_located((By.CSS_SELECTOR, ".user-badge")))
    assert "Guest" in badge.text
    driver.save_screenshot(str(SHOTS / "test_tc4_signed_in_as_guest.png"))
    driver.find_element(By.XPATH, "//button[contains(., 'Logout')]").click()
    wait(driver).until(EC.visibility_of_element_located(SIGN_IN_BTN))


def test_tc5_wrong_password_shows_error(driver):
    wait(driver).until(EC.element_to_be_clickable(SIGN_IN_BTN)).click()
    wait(driver).until(EC.visibility_of_element_located((By.CSS_SELECTOR, ".modal-card")))
    driver.find_element(By.CSS_SELECTOR, ".modal-card input[type='text']").send_keys("no_such_user")
    driver.find_element(By.CSS_SELECTOR, ".modal-card input[type='password']").send_keys("wrongpass123")
    driver.find_element(By.CSS_SELECTOR, ".modal-card button[type='submit']").click()
    error = wait(driver).until(EC.visibility_of_element_located((By.CSS_SELECTOR, ".modal-card .quiz-feedback-box")))
    assert "Invalid username/email or password" in error.text
    assert not driver.find_elements(By.CSS_SELECTOR, ".user-badge")


def test_tc6_notebook_page_navigation(driver):
    wait(driver).until(EC.element_to_be_clickable((By.XPATH, "//a[contains(., 'My Notebook')]"))).click()
    wait(driver).until(EC.url_contains("/notebook"))
    assert driver.current_url.endswith("/notebook")
