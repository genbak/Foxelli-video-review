# Private runtime reference

The application expects the supplied Mrs. Quilty brand book at:

```text
references/private/brand/MRQ-brandbook-July-2024.pdf
```

This PDF is intentionally excluded from Git. Obtain it through the project's approved private delivery channel and preserve the exact filename, or update the Compose mount and `MRQ_BRANDBOOK_PATH` together.

The backend attaches the complete PDF only when a video was uploaded with MRQ context. General reviews do not receive it. The brief, sample videos, evaluation output and development evidence are not runtime dependencies and do not belong in the deployment repository.
