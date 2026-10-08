import io
import os
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from db.session import get_db
from routers.knowledge_builder import router
from schemas.data_building import PrepareRequest, StoreRequest
from services.data_building import extract_pdf, extract_url, prepare_chunks, public_destination, store_document
from services.session_auth import COOKIE_NAME, create_session_token

TEXT = '# Da Nang\n\nDa Nang offers sandy beaches, local food and museums. Visitors can explore the river, markets and nearby mountains. '


class DataBuildingTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            'AUTH_SESSION_SECRET': 'local-unit-test-only',
            'DATA_BUILDING_ADMIN_EMAILS': 'admin@example.com',
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.db = MagicMock()
        self.db.get.return_value = SimpleNamespace(email='admin@example.com', is_active=True)
        self.db.scalar.return_value = None
        app = FastAPI()
        app.include_router(router, prefix='/api')
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)
        self.client.cookies.set(COOKIE_NAME, create_session_token('test-user'))

    def payload(self):
        return StoreRequest(document_type='html', source_location='https://example.com/travel',
            extraction_method='trafilatura', raw_markdown=TEXT, cleaned_markdown=TEXT)

    def test_every_endpoint_requires_authentication(self):
        self.client.cookies.clear()
        for path in ['clean', 'prepare', 'store', 'extract-url', 'extract-pdf']:
            response = self.client.post('/api/data-building/' + path, json={})
            self.assertEqual(response.status_code, 401, path)
        self.assertEqual(self.client.get('/api/data-building/capabilities').status_code, 401)

    def test_capabilities_enforce_admin_account(self):
        self.assertTrue(self.client.get('/api/data-building/capabilities').json()['can_store'])
        self.db.get.return_value.email = 'viewer@example.com'
        self.assertFalse(self.client.get('/api/data-building/capabilities').json()['can_store'])
        response = self.client.post('/api/data-building/store', json=self.payload().model_dump())
        self.assertEqual(response.status_code, 403)
        self.db.add.assert_not_called()

    def test_clean_and_preview_do_not_write(self):
        cleaned = self.client.post('/api/data-building/clean', json={'markdown': TEXT})
        self.assertEqual(cleaned.status_code, 200)
        response = self.client.post('/api/data-building/prepare',
            json={'cleaned_markdown': cleaned.json()['cleaned_markdown']})
        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(response.json()['chunks']), 0)
        self.assertIn('Da Nang', response.json()['chunks'][0]['chunk_text'])
        self.db.add.assert_not_called()
        self.db.commit.assert_not_called()

    def test_invalid_overlap_and_blank_text(self):
        with self.assertRaises(ValidationError):
            PrepareRequest(cleaned_markdown=TEXT, chunk_size=300, chunk_overlap=300)
        with self.assertRaises(HTTPException):
            prepare_chunks(PrepareRequest(cleaned_markdown='   '))
        self.assertEqual(self.client.post('/api/data-building/clean', json={'markdown': '   '}).status_code, 422)

    def test_duplicate_is_not_overwritten(self):
        self.db.scalar.return_value = SimpleNamespace(id='existing')
        response = self.client.post('/api/data-building/store', json=self.payload().model_dump())
        self.assertEqual(response.status_code, 409)
        self.db.add.assert_not_called()

    def test_atomic_embedding_and_storage(self):
        def flush():
            self.db.add.call_args_list[0].args[0].id = uuid.uuid4()
        self.db.flush.side_effect = flush
        model = MagicMock()
        model.encode.return_value = np.zeros((1, 384))
        with patch('core.model_registry.get_embedding_model', return_value=model):
            result = store_document(self.db, self.payload(), 'test-user')
        self.assertEqual(result['saved_chunks'], 1)
        self.db.commit.assert_called_once()
        document, chunk = [call.args[0] for call in self.db.add.call_args_list]
        self.assertEqual(document.extra_metadata['metadata_source'], 'manual')
        self.assertEqual(len(chunk.embedding), 384)
        self.assertFalse(chunk.verified)

    def test_failed_save_rolls_back(self):
        with patch('routers.knowledge_builder.store_document', side_effect=RuntimeError('test')):
            response = self.client.post('/api/data-building/store', json=self.payload().model_dump())
        self.assertEqual(response.status_code, 503)
        self.db.rollback.assert_called_once()
        self.db.commit.assert_not_called()

    def test_pdf_validation_and_extraction(self):
        import pymupdf
        with pymupdf.open() as pdf:
            page = pdf.new_page()
            page.insert_text((40, 40), 'Da Nang has beautiful beaches and tourism museums.')
            content = pdf.tobytes()
        response = self.client.post('/api/data-building/extract-pdf',
            files={'file': ('guide.pdf', io.BytesIO(content), 'application/pdf')})
        self.assertEqual(response.status_code, 200)
        self.assertIn('Da Nang', response.json()['raw_markdown'])
        self.assertEqual(len(response.json()['file_hash']), 64)
        with self.assertRaises(HTTPException):
            extract_pdf(b'not pdf', 'bad.pdf')
        with pymupdf.open() as blank:
            blank.new_page()
            with self.assertRaises(HTTPException):
                extract_pdf(blank.tobytes(), 'scan.pdf')

    def test_url_extraction_methods(self):
        html = '<html><title>Da Nang guide</title><body><article><h1>Da Nang</h1><p>' + TEXT * 10 + '</p></article></body></html>'
        with patch('services.data_building.fetch_public_html', return_value=(html, 'https://example.com')):
            for method in ['trafilatura', 'markdownify']:
                result = extract_url('https://example.com', method)
                self.assertIn('Da Nang', result['raw_markdown'])
                self.assertEqual(result['title'], 'Da Nang guide')

    def test_private_and_metadata_destinations_blocked(self):
        for ip in ['127.0.0.1', '10.0.0.1', '169.254.169.254', '::1', 'fd00::1', '224.0.0.1']:
            with patch('services.data_building.socket.getaddrinfo', return_value=[(0, 0, 0, '', (ip, 443))]):
                with self.assertRaises(HTTPException):
                    public_destination('https://example.com')
        for url in ['file:///etc/passwd', 'http://user:pass@example.com', 'http://example.com:8080']:
            with self.assertRaises(HTTPException):
                public_destination(url)

    def test_redirect_revalidates_destination(self):
        from services.data_building import fetch_public_html
        response = MagicMock(status=302, headers={'Location': 'http://169.254.169.254/latest'})
        pool = MagicMock()
        pool.urlopen.return_value = response
        def addresses(host, port, **kwargs):
            return [(0, 0, 0, '', ('169.254.169.254' if host.startswith('169.') else '93.184.216.34', port))]
        with patch('services.data_building.socket.getaddrinfo', side_effect=addresses), \
                patch('services.data_building.urllib3.HTTPSConnectionPool', return_value=pool):
            with self.assertRaises(HTTPException):
                fetch_public_html('https://example.com')
        pool.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
