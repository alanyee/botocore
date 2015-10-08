# Copyright 2015 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"). You
# may not use this file except in compliance with the License. A copy of
# the License is located at
#
# http://aws.amazon.com/apache2.0/
#
# or in the "license" file accompanying this file. This file is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF
# ANY KIND, either express or implied. See the License for the specific
# language governing permissions and limitations under the License.
from tests import unittest, mock, BaseSessionTest

import botocore.session
from botocore.exceptions import ParamValidationError


class TestS3BucketValidation(unittest.TestCase):
    def test_invalid_bucket_name_raises_error(self):
        session = botocore.session.get_session()
        s3 = session.create_client('s3')
        with self.assertRaises(ParamValidationError):
            s3.put_object(Bucket='adfgasdfadfs/bucket/name',
                          Key='foo', Body=b'asdf')


class BaseS3OperationTest(BaseSessionTest):
    def setUp(self):
        super(BaseS3OperationTest, self).setUp()
        self.region = 'us-west-2'
        self.client = self.session.create_client(
            's3', self.region)
        self.session_send_patch = mock.patch('botocore.endpoint.Session.send')
        self.http_session_send_mock = self.session_send_patch.start()

    def tearDown(self):
        super(BaseSessionTest, self).tearDown()
        self.session_send_patch.stop()


class TestS3GetBucketLifecycle(BaseS3OperationTest):
    def test_multiple_transitions_returns_one(self):
        http_response = mock.Mock()
        http_response.status_code = 200
        http_response.content = (
            '<?xml version="1.0" ?>'
            '<LifecycleConfiguration xmlns="http://s3.amazonaws.'
            'com/doc/2006-03-01/">'
            '	<Rule>'
            '		<ID>transitionRule</ID>'
            '		<Prefix>foo</Prefix>'
            '		<Status>Enabled</Status>'
            '		<Transition>'
            '			<Days>40</Days>'
            '			<StorageClass>STANDARD_IA</StorageClass>'
            '		</Transition>'
            '		<Transition>'
            '			<Days>70</Days>'
            '			<StorageClass>GLACIER</StorageClass>'
            '		</Transition>'
            '	</Rule>'
            '	<Rule>'
            '		<ID>noncurrentVersionRule</ID>'
            '		<Prefix>bar</Prefix>'
            '		<Status>Enabled</Status>'
            '		<NoncurrentVersionTransition>'
            '			<NoncurrentDays>40</NoncurrentDays>'
            '			<StorageClass>STANDARD_IA</StorageClass>'
            '		</NoncurrentVersionTransition>'
            '		<NoncurrentVersionTransition>'
            '			<NoncurrentDays>70</NoncurrentDays>'
            '			<StorageClass>GLACIER</StorageClass>'
            '		</NoncurrentVersionTransition>'
            '	</Rule>'
            '</LifecycleConfiguration>'
        )
        http_response.headers = {}
        self.http_session_send_mock.return_value = http_response
        s3 = self.session.create_client('s3')
        response = s3.get_bucket_lifecycle(Bucket='mybucket')
        # Each Transition member should have at least one of the
        # transitions provided.
        self.assertEqual(
            response['Rules'][0]['Transition'],
            {'Days': 40, 'StorageClass': 'STANDARD_IA'}
        )
        self.assertEqual(
            response['Rules'][1]['NoncurrentVersionTransition'],
            {'NoncurrentDays': 40, 'StorageClass': 'STANDARD_IA'}
        )


class TestS3PutObject(BaseS3OperationTest):
    def test_500_error_with_non_xml_body(self):
        # This test was added because in some use cases, the response
        # returned from S3 is a 500 response which should be retrieved even
        # though the body of the response is in not valid xml such as
        # headers being in the body. From what we can tell, the reason this
        # happens is that the code of the response was probably mutated
        # somewhere when the response was sent to the client, maybe was a
        # proxy's doing and/or how expect 100's are treated,
        # but a 200 response is mutated to have a 500 response code.
        non_xml_content = (
            'x-amz-id-2: foo\r\n'
            'x-amz-request-id: bar\n'
            'Date: Tue, 06 Oct 2015 03:20:38 GMT\r\n'
            'ETag: "a6d856bc171fc6aa1b236680856094e2"\r\n'
            'Content-Length: 0\r\n'
            'Server: AmazonS3\r\n'
        )
        http_500_response = mock.Mock()
        http_500_response.status_code = 500
        http_500_response.content = non_xml_content
        http_500_response.headers = {}

        success_response = mock.Mock()
        success_response.status_code = 200
        success_response.content = b''
        success_response.headers = {}

        self.http_session_send_mock.side_effect = [
            http_500_response, success_response
        ]
        s3 = self.session.create_client('s3')
        response = s3.put_object(Bucket='mybucket', Key='mykey', Body=b'foo')
        # The first response should have been retried even though the xml is
        # invalid and eventually return the 200 response.
        self.assertEqual(response['ResponseMetadata']['HTTPStatusCode'], 200)
