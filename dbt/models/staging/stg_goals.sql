-- One row per goal event. The source is inconsistent about `minute`
-- (int in most years, strings like "45+3" in 2026), so it is normalized
-- here into a numeric minute plus a stoppage offset, keeping the raw form.

with payloads as (

    select
        year,
        cast(json_extract(payload, '$.matches') as json[]) as matches
    from {{ source('raw', 'raw_payloads') }}

),

matches as (

    select
        year,
        generate_subscripts(matches, 1) as file_pos,
        unnest(matches)                 as m
    from payloads

),

sides as (

    select
        year,
        coalesce(try_cast(json_extract_string(m, '$.num') as integer), file_pos) as match_id,
        side,
        json_extract_string(m, '$.team' || side)                as team,
        cast(json_extract(m, '$.goals' || side) as json[])      as goal_list
    from matches
    cross join (values (1), (2)) as s(side)

),

goal_events as (

    select
        year,
        match_id,
        side,
        team,
        generate_subscripts(goal_list, 1) as goal_index,
        unnest(goal_list)                 as g
    from sides

)

select
    year,
    match_id,
    year || '-' || match_id                                   as match_key,
    year || '-' || match_id || '-' || side || '-' || goal_index as goal_key,
    team,
    json_extract_string(g, '$.name')                          as scorer,
    json_extract_string(g, '$.minute')                        as minute_raw,
    try_cast(regexp_extract(json_extract_string(g, '$.minute'), '^(\d+)', 1) as integer) as minute,
    try_cast(regexp_extract(json_extract_string(g, '$.minute'), '\+(\d+)$', 1) as integer) as stoppage_offset,
    coalesce(try_cast(json_extract_string(g, '$.penalty') as boolean), false) as is_penalty,
    coalesce(try_cast(json_extract_string(g, '$.owngoal') as boolean), false) as is_owngoal
from goal_events
