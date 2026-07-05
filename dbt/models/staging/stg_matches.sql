-- One row per match, parsed and typed from the raw JSON payloads.
-- match_id comes from the source's `num` when present, else file position.

with payloads as (

    select
        year,
        cast(json_extract(payload, '$.matches') as json[]) as matches
    from {{ source('raw', 'raw_payloads') }}

),

unnested as (

    select
        year,
        generate_subscripts(matches, 1) as file_pos,
        unnest(matches)                 as m
    from payloads

)

select
    year,
    coalesce(try_cast(json_extract_string(m, '$.num') as integer), file_pos) as match_id,
    year || '-' || coalesce(try_cast(json_extract_string(m, '$.num') as integer), file_pos) as match_key,
    json_extract_string(m, '$.round')  as round,
    case when json_extract(m, '$.group') is not null then 'group' else 'knockout' end as stage,
    json_extract_string(m, '$.group')  as match_group,
    try_cast(json_extract_string(m, '$.date') as date) as match_date,
    json_extract_string(m, '$.team1')  as team1,
    json_extract_string(m, '$.team2')  as team2,
    try_cast(json_extract_string(m, '$.score.ft[0]') as integer) as score1_ft,
    try_cast(json_extract_string(m, '$.score.ft[1]') as integer) as score2_ft,
    try_cast(json_extract_string(m, '$.score.et[0]') as integer) as score1_et,
    try_cast(json_extract_string(m, '$.score.et[1]') as integer) as score2_et,
    try_cast(json_extract_string(m, '$.score.p[0]')  as integer) as score1_p,
    try_cast(json_extract_string(m, '$.score.p[1]')  as integer) as score2_p,
    json_extract(m, '$.score') is not null as played
from unnested
