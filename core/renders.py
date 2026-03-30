import re

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
        response = renderer_context.get("response") if renderer_context else None

        status_code = response.status_code if response else 200
        is_success = status_code < 400

        message = "Operation successful"

        if not is_success:
            raw_error = None
            if isinstance(data, str):
                raw_error = data
            elif isinstance(data, list) and len(data) > 0 and isinstance(data[0], str):
                raw_error = data.pop(0)

            if raw_error:
                match = re.search(r'":"(.*?)"\}', raw_error)
                if match:
                    message = match.group(1)
                else:
                    message = (
                        raw_error.replace("{", "")
                        .replace("}", "")
                        .replace('"', "")
                        .replace("\\", "")
                    )

            elif isinstance(data, dict):
                if "non_field_errors" in data:
                    errors = data.get("non_field_errors")
                    message = errors[0] if isinstance(errors, list) else errors
                elif "detail" in data:
                    message = data.get("detail")
                elif "error" in data:
                    message = data.get("error")
                else:
                    message = "unknown error occurred"

        if status_code == 204:
            data = None

        standardized_data = {
            "success": is_success,
            "message": message,
            "data": data if is_success else None,
        }

        if not is_success:
            standardized_data["errors"] = data
            standardized_data["code"] = f"ERROR_{response.status_code}"

        elif isinstance(data, dict) and "results" in data:
            standardized_data["data"] = data["results"]
            standardized_data["meta"] = {
                "count": data.get("count"),
                "next": data.get("next"),
                "previous": data.get("previous"),
            }

        return super().render(standardized_data, accepted_media_type, renderer_context)
