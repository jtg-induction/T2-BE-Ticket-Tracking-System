from rest_framework.renderers import JSONRenderer


class StandardizedJSONRenderer(JSONRenderer):
    """
    Renderer to envelope all API responses in a consistent JSON structure.
    """

    def render(self, data, accepted_media_type=None, renderer_context=None):
        """
        Wraps response data in a standard envelope.

        Args:
            data: Raw response data from the view or serializer.
            accepted_media_type: Requested media type.
            renderer_context: Context including the 'response' object and status.

        Returns:
            Serialized JSON with keys: success, message, data, errors, and meta.
        """
        response = renderer_context.get("response")

        if response.status_code == 204:
            data = None

        standardized_data = {
            "success": response.status_code < 400,
            "message": "Operation successful"
            if response.status_code < 400
            else "An error occurred",
            "data": data if response.status_code < 400 else None,
        }

        if response.status_code >= 400:
            standardized_data["errors"] = data
            standardized_data["code"] = f"ERROR_{response.status_code}"

        if isinstance(data, dict) and "results" in data:
            standardized_data["data"] = data["results"]
            standardized_data["meta"] = {
                "count": data.get("count"),
                "next": data.get("next"),
                "previous": data.get("previous"),
            }

        return super().render(standardized_data, accepted_media_type, renderer_context)
