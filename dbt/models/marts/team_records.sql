-- All-time record per team across every tournament. Historical entities
-- stay distinct on purpose (West Germany vs Germany, Soviet Union, etc.).

with sides as (

    select year, team1 as team, goals1 as goals_for, goals2 as goals_against, winner
    from {{ ref('int_match_outcomes') }}

    union all

    select year, team2 as team, goals2 as goals_for, goals1 as goals_against, winner
    from {{ ref('int_match_outcomes') }}

)

select
    team,
    count(distinct year)                                     as tournaments,
    min(year)                                                as first_year,
    max(year)                                                as last_year,
    count(*)                                                 as played,
    count(*) filter (where winner = team)                    as won,
    count(*) filter (where winner is null)                   as drawn,
    count(*) filter (where winner is not null and winner != team) as lost,
    sum(goals_for)                                           as goals_for,
    sum(goals_against)                                       as goals_against,
    round(count(*) filter (where winner = team) * 1.0 / count(*), 3) as win_rate
from sides
group by team
order by won desc, played desc
