-- Explicit widths keep Chinese pipe-table cells inside the printable text area.
function Table(tab)
  local widths = nil
  if #tab.colspecs == 2 then
    widths = {0.34, 0.66}
  elseif #tab.colspecs == 3 then
    widths = {0.28, 0.40, 0.32}
  end
  if widths then
    for i, spec in ipairs(tab.colspecs) do
      tab.colspecs[i] = {spec[1], widths[i]}
    end
  end
  return tab
end
