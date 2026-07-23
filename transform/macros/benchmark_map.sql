{#
  Per-exchange buy-and-hold benchmark, as a joinable relation. Sourced from the
  `benchmarks` var so the mapping lives in one place; quantpulse.data.calendar holds the
  same fact for the Python side and a unit test asserts the two agree.
#}
{% macro benchmark_map() %}
    {%- set benchmarks = var('benchmarks') -%}
    {%- for exchange, ticker in benchmarks.items() %}
    select '{{ exchange }}' as exchange, '{{ ticker }}' as benchmark_ticker
    {%- if not loop.last %}
    union all
    {%- endif %}
    {%- endfor %}
{% endmacro %}
