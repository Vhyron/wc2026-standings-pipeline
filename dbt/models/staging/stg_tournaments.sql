select
    year,
    coalesce(json_extract_string(payload, '$.name'), 'World Cup ' || year) as name
from {{ source('raw', 'raw_payloads') }}
