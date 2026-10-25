"""Exercise real Range response logic without network or external services."""
from io import BytesIO
import unittest
from backend.server import Handler


class VideoRangeTests(unittest.TestCase):
    def response(self, value=None):
        handler=object.__new__(Handler)
        handler.headers={} if value is None else {'Range':value}
        handler.wfile=BytesIO();headers={};statuses=[]
        handler.send_response=statuses.append
        handler.send_header=lambda name,value:headers.update({name:value})
        handler.end_headers=lambda:None
        handler._send_video(b'0123456789','video/mp4')
        return statuses[0],headers,handler.wfile.getvalue()

    def test_full_file(self):
        status,headers,body=self.response()
        self.assertEqual((status,body),(200,b'0123456789'))
        self.assertEqual(headers['Accept-Ranges'],'bytes')

    def test_startup_probe_and_seek(self):
        for value,body,span in [('bytes=0-1',b'01','0-1'),('bytes=5-',b'56789','5-9'),
                                ('bytes=-3',b'789','7-9'),('bytes=8-100',b'89','8-9')]:
            with self.subTest(value=value):
                status,headers,received=self.response(value)
                self.assertEqual((status,received),(206,body))
                self.assertEqual(headers['Content-Range'],'bytes '+span+'/10')
                self.assertEqual(int(headers['Content-Length']),len(body))

    def test_invalid_ranges(self):
        for value in ('bytes=11-','bytes=6-2','bytes=-0','bytes=-','bytes=0-1,4-5'):
            with self.subTest(value=value):
                status,headers,body=self.response(value)
                self.assertEqual((status,body),(416,b''))
                self.assertEqual(headers['Content-Range'],'bytes */10')
