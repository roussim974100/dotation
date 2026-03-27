$ErrorActionPreference = "Stop"

$cp1252 = [System.Text.Encoding]::GetEncoding(1252)
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

$files = Get-ChildItem "frontend" -Recurse -File | Where-Object {
  $_.Extension -in ".html", ".js", ".css", ".md"
}

foreach ($file in $files) {
  $bytes = [System.IO.File]::ReadAllBytes($file.FullName)
  $text1252 = $cp1252.GetString($bytes)
  $fixed = [System.Text.Encoding]::UTF8.GetString($cp1252.GetBytes($text1252))
  [System.IO.File]::WriteAllText($file.FullName, $fixed, $utf8NoBom)
}
