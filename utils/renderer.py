from rest_framework.renderers import JSONRenderer

class LoggingJSONRenderer(JSONRenderer):
    def render(self, data, accepted_media_type=None, renderer_context=None):
        print("[DRF RENDERED DATA]", data)
        return super().render(data, accepted_media_type, renderer_context)
