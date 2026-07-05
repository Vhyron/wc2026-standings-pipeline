-- Group-stage standings for every tournament, using the points rule of
-- each era (2 per win before 1994, 3 since).

select
    year,
    match_group,
    team,
    count(*)                                    as played,
    count(*) filter (where result = 'win')      as won,
    count(*) filter (where result = 'draw')     as drawn,
    count(*) filter (where result = 'loss')     as lost,
    sum(goals_for)                              as goals_for,
    sum(goals_against)                          as goals_against,
    sum(goals_for) - sum(goals_against)         as goal_difference,
    sum(points)                                 as points,
    row_number() over (
        partition by year, match_group
        order by sum(points) desc,
                 sum(goals_for) - sum(goals_against) desc,
                 sum(goals_for) desc,
                 team
    ) as position
from {{ ref('int_team_match_results') }}
where stage = 'group'
group by year, match_group, team
