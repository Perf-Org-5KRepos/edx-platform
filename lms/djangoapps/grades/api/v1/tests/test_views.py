"""
Tests for v1 views
"""
from datetime import datetime
import ddt
import json
import unittest
try:
    import urllib.parse as urllib
except ImportError:
    import urllib

from django.core.urlresolvers import reverse
from django.test import TestCase
from django.conf import settings
from django.test.utils import override_settings
from mock import MagicMock, patch
from opaque_keys import InvalidKeyError
from pytz import UTC
from rest_framework import status
from rest_framework.test import APITestCase

from capa.tests.response_xml_factory import MultipleChoiceResponseXMLFactory
from edx_oauth2_provider.tests.factories import AccessTokenFactory, ClientFactory
from edx_oauth2_provider.tests.base import BaseTestCase
from lms.djangoapps.courseware.tests.factories import GlobalStaffFactory, StaffFactory
from student.tests.factories import CourseEnrollmentFactory, UserFactory
from openedx.core.djangoapps.oauth_dispatch.tests import mixins
from xmodule.modulestore import ModuleStoreEnum
from xmodule.modulestore.tests.factories import CourseFactory, ItemFactory
from xmodule.modulestore.tests.django_utils import SharedModuleStoreTestCase, TEST_DATA_SPLIT_MODULESTORE


class GradeViewTestMixin(SharedModuleStoreTestCase):
    """
    Mixin class for grades related view tests

    The following tests assume that the grading policy is the edX default one:
    {
        "GRADER": [
            {
                "drop_count": 2,
                "min_count": 12,
                "short_label": "HW",
                "type": "Homework",
                "weight": 0.15
            },
            {
                "drop_count": 2,
                "min_count": 12,
                "type": "Lab",
                "weight": 0.15
            },
            {
                "drop_count": 0,
                "min_count": 1,
                "short_label": "Midterm",
                "type": "Midterm Exam",
                "weight": 0.3
            },
            {
                "drop_count": 0,
                "min_count": 1,
                "short_label": "Final",
                "type": "Final Exam",
                "weight": 0.4
            }
        ],
        "GRADE_CUTOFFS": {
            "Pass": 0.5
        }
    }
    """
    MODULESTORE = TEST_DATA_SPLIT_MODULESTORE

    @classmethod
    def setUpClass(cls):
        super(GradeViewTestMixin, cls).setUpClass()

        cls.course = CourseFactory.create(display_name='test course', run="Testing_course")

        chapter = ItemFactory.create(
            category='chapter',
            parent_location=cls.course.location,
            display_name="Chapter 1",
        )
        # create a problem for each type and minimum count needed by the grading policy
        # A section is not considered if the student answers less than "min_count" problems
        for grading_type, min_count in (("Homework", 12), ("Lab", 12), ("Midterm Exam", 1), ("Final Exam", 1)):
            for num in xrange(min_count):
                section = ItemFactory.create(
                    category='sequential',
                    parent_location=chapter.location,
                    due=datetime(2013, 9, 18, 11, 30, 00),
                    display_name='Sequential {} {}'.format(grading_type, num),
                    format=grading_type,
                    graded=True,
                )
                vertical = ItemFactory.create(
                    category='vertical',
                    parent_location=section.location,
                    display_name='Vertical {} {}'.format(grading_type, num),
                )
                ItemFactory.create(
                    category='problem',
                    parent_location=vertical.location,
                    display_name='Problem {} {}'.format(grading_type, num),
                )

        cls.course_key = cls.course.id

        cls.password = 'test'
        cls.student = UserFactory(username='dummy', password=cls.password)
        cls.other_student = UserFactory(username='foo', password=cls.password)
        cls.other_user = UserFactory(username='bar', password=cls.password)
        cls.staff = StaffFactory(course_key=cls.course_key, password=cls.password)
        cls.global_staff = GlobalStaffFactory.create()
        date = datetime(2013, 1, 22, tzinfo=UTC)
        for user in (cls.student, cls.other_student,):
            CourseEnrollmentFactory(
                course_id=cls.course.id,
                user=user,
                created=date,
            )

    def setUp(self):
        super(GradeViewTestMixin, self).setUp()
        self.client.login(username=self.student.username, password=self.password)

    @classmethod
    def _create_test_course_with_default_grading_policy(cls, display_name, run):
        course = CourseFactory.create(display_name=display_name, run=run)

        chapter = ItemFactory.create(
            category='chapter',
            parent_location=course.location,
            display_name="Chapter 1",
        )
        # create a problem for each type and minimum count needed by the grading policy
        # A section is not considered if the student answers less than "min_count" problems
        for grading_type, min_count in (("Homework", 12), ("Lab", 12), ("Midterm Exam", 1), ("Final Exam", 1)):
            for num in xrange(min_count):
                section = ItemFactory.create(
                    category='sequential',
                    parent_location=chapter.location,
                    due=datetime(2017, 12, 18, 11, 30, 00),
                    display_name='Sequential {} {}'.format(grading_type, num),
                    format=grading_type,
                    graded=True,
                )
                vertical = ItemFactory.create(
                    category='vertical',
                    parent_location=section.location,
                    display_name='Vertical {} {}'.format(grading_type, num),
                )
                ItemFactory.create(
                    category='problem',
                    parent_location=vertical.location,
                    display_name='Problem {} {}'.format(grading_type, num),
                )

        return course


@ddt.ddt
class CurrentGradeViewTest(GradeViewTestMixin, APITestCase):
    """
    Tests for grades related to a course
        i.e. /api/grades/v1/course_grade/{course_id}/users/{username}=(student)
    """

    @classmethod
    def setUpClass(cls):
        super(CurrentGradeViewTest, cls).setUpClass()
        cls.namespaced_url = 'grades_api:v1:user_grade_detail'

    def setUp(self):
        super(CurrentGradeViewTest, self).setUp()

    def get_url(self, username):
        """
        Helper function to create the url
        """
        base_url = reverse(
            self.namespaced_url,
            kwargs={
                'course_id': self.course_key,
            }
        )
        return "{0}?username={1}".format(base_url, username)

    def test_anonymous(self):
        """
        Test that an anonymous user cannot access the API and an error is received.
        """
        self.client.logout()
        resp = self.client.get(self.get_url(self.student.username))
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_self_get_grade(self):
        """
        Test that a user can successfully request her own grade.
        """
        resp = self.client.get(self.get_url(self.student.username))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_nonexistent_user(self):
        """
        Test that a request for a nonexistent username returns an error.
        """
        self.client.logout()
        self.client.login(username=self.staff.username, password=self.password)
        resp = self.client.get(self.get_url('IDoNotExist'))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn('error_code', resp.data)  # pylint: disable=no-member
        self.assertEqual(resp.data['error_code'], 'user_does_not_exist')  # pylint: disable=no-member

    def test_other_get_grade(self):
        """
        Test that if a user requests the grade for another user, she receives an error.
        """
        self.client.logout()
        self.client.login(username=self.other_student.username, password=self.password)
        resp = self.client.get(self.get_url(self.student.username))
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('error_code', resp.data)  # pylint: disable=no-member
        self.assertEqual(resp.data['error_code'], 'user_mismatch')  # pylint: disable=no-member

    def test_self_get_grade_not_enrolled(self):
        """
        Test that a user receives an error if she requests
        her own grade in a course where she is not enrolled.
        """
        # a user not enrolled in the course cannot request her grade
        self.client.logout()
        self.client.login(username=self.other_user.username, password=self.password)
        resp = self.client.get(self.get_url(self.other_user.username))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn('error_code', resp.data)  # pylint: disable=no-member
        self.assertEqual(
            resp.data['error_code'],  # pylint: disable=no-member
            'user_or_course_does_not_exist'
        )

    def test_no_grade(self):
        """
        Test the grade for a user who has not answered any test.
        """
        resp = self.client.get(self.get_url(self.student.username))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        expected_data = [{
            'user': self.student.username,
            'course_key': str(self.course_key),
            'passed': False,
            'percent': 0.0,
            'letter_grade': None
        }]

        self.assertEqual(resp.data, expected_data)  # pylint: disable=no-member

    def test_wrong_course_key(self):
        """
        Test that a request for an invalid course key returns an error.
        """
        def mock_from_string(*args, **kwargs):  # pylint: disable=unused-argument
            """Mocked function to always raise an exception"""
            raise InvalidKeyError('foo', 'bar')

        with patch('opaque_keys.edx.keys.CourseKey.from_string', side_effect=mock_from_string):
            resp = self.client.get(self.get_url(self.student.username))

        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn('error_code', resp.data)  # pylint: disable=no-member
        self.assertEqual(
            resp.data['error_code'],  # pylint: disable=no-member
            'invalid_course_key'
        )

    def test_course_does_not_exist(self):
        """
        Test that requesting a valid, nonexistent course key returns an error as expected.
        """
        base_url = reverse(
            self.namespaced_url,
            kwargs={
                'course_id': 'course-v1:MITx+8.MechCX+2014_T1',
            }
        )
        url = "{0}?username={1}".format(base_url, self.student.username)
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn('error_code', resp.data)  # pylint: disable=no-member
        self.assertEqual(
            resp.data['error_code'],  # pylint: disable=no-member
            'user_or_course_does_not_exist'
        )

    @ddt.data(
        ({'letter_grade': None, 'percent': 0.4, 'passed': False}),
        ({'letter_grade': 'Pass', 'percent': 1, 'passed': True}),
    )
    def test_grade(self, grade):
        """
        Test that the user gets her grade in case she answered tests with an insufficient score.
        """
        with patch('lms.djangoapps.grades.new.course_grade.CourseGradeFactory.get_persisted') as mock_grade:
            grade_fields = {
                'letter_grade': grade['letter_grade'],
                'percent': grade['percent'],
                'passed': grade['letter_grade'] is not None,

            }
            mock_grade.return_value = MagicMock(**grade_fields)
            resp = self.client.get(self.get_url(self.student.username))

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        expected_data = {
            'user': unicode(self.student.username),
            'course_key': str(self.course_key),
        }

        expected_data.update(grade)
        self.assertEqual(resp.data, [expected_data])  # pylint: disable=no-member

    @ddt.data(
        'staff', 'global_staff'
    )
    def test_staff_can_see_student(self, staff_user):
        """
        Ensure that staff members can see her student's grades.
        """
        self.client.logout()
        self.client.login(username=getattr(self, staff_user).username, password=self.password)
        resp = self.client.get(self.get_url(self.student.username))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        expected_data = [{
            'user': self.student.username,
            'letter_grade': None,
            'percent': 0.0,
            'course_key': str(self.course_key),
            'passed': False
        }]
        self.assertEqual(resp.data, expected_data)  # pylint: disable=no-member


@ddt.ddt
class CourseGradeAllUsersViewTest(GradeViewTestMixin, APITestCase):
    """
    Tests for grades related to a user
        i.e. /api/grades/v1/course_grade/{course_id}/all_users
    """

    @classmethod
    def setUpClass(cls):
        super(CourseGradeAllUsersViewTest, cls).setUpClass()
        cls.namespaced_url = 'grades_api:v1:course_grades_all'

    def setUp(self):
        super(CourseGradeAllUsersViewTest, self).setUp()

    def get_url(self):
        """
        Helper function to create the url
        """
        base_url = reverse(
            self.namespaced_url,
            kwargs={
                'course_id': self.course_key,
            }
        )

        return base_url

    def test_anonymous(self):
        self.client.logout()
        resp = self.client.get(self.get_url())
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_student_forbidden(self):
        resp = self.client.get(self.get_url())
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    @ddt.data(
        'staff', 'global_staff'
    )
    def test_staff_forbidden(self, staff_user):
        self.client.logout()
        self.client.login(username=getattr(self, staff_user).username, password=self.password)
        resp = self.client.get(self.get_url())
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


@ddt.ddt
class CourseGradeAllUsersClientcredentialTest(BaseTestCase, GradeViewTestMixin, APITestCase):

    def setUp(self):
        super(CourseGradeAllUsersClientcredentialTest, self).setUp()

    def login_and_authorize(self, scope=None, claims=None, trusted=False, validate_session=True):
        """ Login into client using OAuth2 authorization flow. """

        self.set_trusted(self.auth_client, trusted)
        self.client.login(username=self.user.username, password=self.password)

        client_id = self.auth_client.client_id
        payload = {
            'client_id': client_id,
            'redirect_uri': self.auth_client.redirect_uri,
            'response_type': 'code',
            'state': 'some_state',
        }
        _add_values(payload, 'id_token', scope, claims)

        response = self.client.get(reverse('oauth2:capture'), payload)
        self.assertEqual(302, response.status_code)

        response = self.client.get(reverse('oauth2:authorize'), payload)

        if validate_session:
            self.assertListEqual(self.client.session[AUTHORIZED_CLIENTS_SESSION_KEY], [client_id])

        return response

    def get_access_token_response(self, scope=None, claims=None):
        """ Get a new access token using the OAuth2 authorization flow. """
        response = self.login_and_authorize(scope, claims, trusted=True)
        self.assertEqual(302, response.status_code)
        self.assertEqual(reverse('oauth2:redirect'), normpath(response['Location']))

        response = self.client.get(reverse('oauth2:redirect'))
        self.assertEqual(302, response.status_code)

        query = QueryDict(urlparse(response['Location']).query)

        payload = {
            'grant_type': 'client_credentials',
            'client_id': self.auth_client.client_id,
            'client_secret': self.client_secret,
            'code': query['code'],
        }
        _add_values(payload, 'id_token', scope, claims)

        response = self.client.post(reverse('oauth2:access_token'), payload)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


@ddt.ddt
class GradingPolicyTestMixin(object):
    """
    Mixin class for Grading Policy tests
    """
    view_name = None

    def setUp(self):
        super(GradingPolicyTestMixin, self).setUp()
        self.create_user_and_access_token()

    def create_user_and_access_token(self):
        # pylint: disable=missing-docstring
        self.user = GlobalStaffFactory.create()
        self.oauth_client = ClientFactory.create()
        self.access_token = AccessTokenFactory.create(user=self.user, client=self.oauth_client).token

    @classmethod
    def create_course_data(cls):
        # pylint: disable=missing-docstring
        cls.invalid_course_id = 'foo/bar/baz'
        cls.course = CourseFactory.create(display_name='An Introduction to API Testing', raw_grader=cls.raw_grader)
        cls.course_id = unicode(cls.course.id)
        with cls.store.bulk_operations(cls.course.id, emit_signals=False):
            cls.sequential = ItemFactory.create(
                category="sequential",
                parent_location=cls.course.location,
                display_name="Lesson 1",
                format="Homework",
                graded=True
            )

            factory = MultipleChoiceResponseXMLFactory()
            args = {'choices': [False, True, False]}
            problem_xml = factory.build_xml(**args)
            cls.problem = ItemFactory.create(
                category="problem",
                parent_location=cls.sequential.location,
                display_name="Problem 1",
                format="Homework",
                data=problem_xml,
            )

            cls.video = ItemFactory.create(
                category="video",
                parent_location=cls.sequential.location,
                display_name="Video 1",
            )

            cls.html = ItemFactory.create(
                category="html",
                parent_location=cls.sequential.location,
                display_name="HTML 1",
            )

    def http_get(self, uri, **headers):
        """
        Submit an HTTP GET request
        """

        default_headers = {
            'HTTP_AUTHORIZATION': 'Bearer ' + self.access_token
        }
        default_headers.update(headers)

        response = self.client.get(uri, follow=True, **default_headers)
        return response

    def assert_get_for_course(self, course_id=None, expected_status_code=200, **headers):
        """
        Submit an HTTP GET request to the view for the given course.
        Validates the status_code of the response is as expected.
        """

        response = self.http_get(
            reverse(self.view_name, kwargs={'course_id': course_id or self.course_id}),
            **headers
        )
        self.assertEqual(response.status_code, expected_status_code)
        return response

    def get_auth_header(self, user):
        """
        Returns Bearer auth header with a generated access token
        for the given user.
        """
        access_token = AccessTokenFactory.create(user=user, client=self.oauth_client).token
        return 'Bearer ' + access_token

    def test_get_invalid_course(self):
        """
        The view should return a 404 for an invalid course ID.
        """
        self.assert_get_for_course(course_id=self.invalid_course_id, expected_status_code=404)

    def test_get(self):
        """
        The view should return a 200 for a valid course ID.
        """
        return self.assert_get_for_course()

    def test_not_authenticated(self):
        """
        The view should return HTTP status 401 if user is unauthenticated.
        """
        self.assert_get_for_course(expected_status_code=401, HTTP_AUTHORIZATION=None)

    def test_staff_authorized(self):
        """
        The view should return a 200 when provided an access token
        for course staff.
        """
        user = StaffFactory(course_key=self.course.id)
        auth_header = self.get_auth_header(user)
        self.assert_get_for_course(HTTP_AUTHORIZATION=auth_header)

    def test_not_authorized(self):
        """
        The view should return HTTP status 404 when provided an
        access token for an unauthorized user.
        """
        user = UserFactory()
        auth_header = self.get_auth_header(user)
        self.assert_get_for_course(expected_status_code=404, HTTP_AUTHORIZATION=auth_header)

    @ddt.data(ModuleStoreEnum.Type.mongo, ModuleStoreEnum.Type.split)
    def test_course_keys(self, modulestore_type):
        """
        The view should be addressable by course-keys from both module stores.
        """
        course = CourseFactory.create(
            start=datetime(2014, 6, 16, 14, 30),
            end=datetime(2015, 1, 16),
            org="MTD",
            default_store=modulestore_type,
        )
        self.assert_get_for_course(course_id=unicode(course.id))


class CourseGradingPolicyTests(GradingPolicyTestMixin, SharedModuleStoreTestCase):
    """
    Tests for CourseGradingPolicy view.
    """
    view_name = 'grades_api:course_grading_policy'

    raw_grader = [
        {
            "min_count": 24,
            "weight": 0.2,
            "type": "Homework",
            "drop_count": 0,
            "short_label": "HW"
        },
        {
            "min_count": 4,
            "weight": 0.8,
            "type": "Exam",
            "drop_count": 0,
            "short_label": "Exam"
        }
    ]

    @classmethod
    def setUpClass(cls):
        super(CourseGradingPolicyTests, cls).setUpClass()
        cls.create_course_data()

    def test_get(self):
        """
        The view should return grading policy for a course.
        """
        response = super(CourseGradingPolicyTests, self).test_get()

        expected = [
            {
                "count": 24,
                "weight": 0.2,
                "assignment_type": "Homework",
                "dropped": 0
            },
            {
                "count": 4,
                "weight": 0.8,
                "assignment_type": "Exam",
                "dropped": 0
            }
        ]
        self.assertListEqual(response.data, expected)


class CourseGradingPolicyMissingFieldsTests(GradingPolicyTestMixin, SharedModuleStoreTestCase):
    """
    Tests for CourseGradingPolicy view when fields are missing.
    """
    view_name = 'grades_api:course_grading_policy'

    # Raw grader with missing keys
    raw_grader = [
        {
            "min_count": 24,
            "weight": 0.2,
            "type": "Homework",
            "drop_count": 0,
            "short_label": "HW"
        },
        {
            # Deleted "min_count" key
            "weight": 0.8,
            "type": "Exam",
            "drop_count": 0,
            "short_label": "Exam"
        }
    ]

    @classmethod
    def setUpClass(cls):
        super(CourseGradingPolicyMissingFieldsTests, cls).setUpClass()
        cls.create_course_data()

    def test_get(self):
        """
        The view should return grading policy for a course.
        """
        response = super(CourseGradingPolicyMissingFieldsTests, self).test_get()

        expected = [
            {
                "count": 24,
                "weight": 0.2,
                "assignment_type": "Homework",
                "dropped": 0
            },
            {
                "count": None,
                "weight": 0.8,
                "assignment_type": "Exam",
                "dropped": 0
            }
        ]
        self.assertListEqual(response.data, expected)
