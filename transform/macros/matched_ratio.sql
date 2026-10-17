{#- A ratio of two flow lines over the same months (ADR 0007): twelve months against twelve months
    when both reach the same quarter, otherwise fiscal year against fiscal year, otherwise none.
    Expects `<line>_ttm`, `<line>_through`, `<line>_fy` and `<line>_fy_end` columns on `rel`. -#}
{% macro matched_ratio(rel, top, bottom) -%}
case
    when {{ rel }}.{{ top }}_through = {{ rel }}.{{ bottom }}_through
        then {{ rel }}.{{ top }}_ttm / nullif({{ rel }}.{{ bottom }}_ttm, 0)
    when {{ rel }}.{{ top }}_fy_end = {{ rel }}.{{ bottom }}_fy_end
        then {{ rel }}.{{ top }}_fy / nullif({{ rel }}.{{ bottom }}_fy, 0)
end
{%- endmacro %}
