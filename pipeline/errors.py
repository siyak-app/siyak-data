"""The pipeline's single error type."""


class PipelineError(Exception):
    """A failure the user can act on; the CLI prints it without a traceback."""
