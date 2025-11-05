param(
  [string]$SourceDir = "data\raw_videos",
  [string]$OutDir   = "data\audio"
)

# 允许的媒体后缀
$allowed = @('.mp4','.mov','.mkv','.m4a','.mp3','.wav')

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

# 递归遍历所有视频/音频文件
Get-ChildItem -Path $SourceDir -Recurse -File | Where-Object {
  $allowed -contains $_.Extension.ToLower()
} | ForEach-Object {
  $src  = $_.FullName
  $stem = [IO.Path]::GetFileNameWithoutExtension($_.Name)

  # 若不同文件夹下有同名文件，用父目录名作前缀，避免覆盖
  $parent = Split-Path $_.DirectoryName -Leaf
  $dstName = "$stem.wav"
  if (Test-Path (Join-Path $OutDir $dstName) -and $parent) {
    $dstName = "${parent}_$stem.wav"
  }
  $dst = Join-Path $OutDir $dstName

  if (Test-Path $dst) {
    Write-Host "skip (exists): $dst"
    return
  }

  Write-Host ">> ffmpeg => $dst"
  & ffmpeg -hide_banner -nostdin -y -i $src -ac 1 -ar 16000 $dst
}
