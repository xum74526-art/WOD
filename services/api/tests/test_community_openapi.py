import unittest

from app.main import app


class CommunityOpenApiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = app.openapi()
        cls.schemas = cls.document["components"]["schemas"]

    def response_schema_ref(self, path: str, method: str) -> str:
        response = self.document["paths"][path][method]["responses"]["200"]
        return response["content"]["application/json"]["schema"]["$ref"]

    def test_post_endpoints_publish_typed_envelopes(self):
        self.assertEqual(
            self.response_schema_ref("/api/community/posts", "get"),
            "#/components/schemas/PostListResponse",
        )
        self.assertEqual(
            self.response_schema_ref("/api/community/posts", "post"),
            "#/components/schemas/PostResponse",
        )
        self.assertEqual(
            self.response_schema_ref("/api/community/posts/{pid}", "get"),
            "#/components/schemas/PostResponse",
        )
        fields = self.schemas["PostOut"]["properties"]
        for field in ("author_name", "author_avatar", "is_liked", "is_following", "is_own"):
            self.assertIn(field, fields)

    def test_comment_endpoints_publish_typed_envelopes(self):
        self.assertEqual(
            self.response_schema_ref("/api/community/posts/{pid}/comments", "get"),
            "#/components/schemas/CommentListResponse",
        )
        self.assertEqual(
            self.response_schema_ref("/api/community/posts/{pid}/comments", "post"),
            "#/components/schemas/CommentResponse",
        )
        fields = self.schemas["CommentOut"]["properties"]
        for field in ("author_name", "post_comments", "is_own"):
            self.assertIn(field, fields)


if __name__ == "__main__":
    unittest.main()
