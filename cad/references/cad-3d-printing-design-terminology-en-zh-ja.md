# CAD, 3D Printing, And Optical Holder Terminology

This note teaches the English phrasing for recent CAD/3D-printing design work,
with Chinese and Japanese equivalents. It focuses on C-mount adapters, sensor
holders, PCB pockets, connector clearances, threads, cages, light valves, and
print-fit tolerance.

## How To Describe Position

| Idea | Good English | 中文 | 日本語 |
| --- | --- | --- | --- |
| long side of a board | long edge / long side | 长边 | 長辺（ちょうへん） |
| short side of a board | short edge / short side | 短边 | 短辺（たんぺん） |
| in the long direction | along the long edge / in the long-edge direction | 沿长边方向 | 長辺方向に |
| parallel to the long edge | parallel to the long edge | 与长边平行 | 長辺に平行 |
| opposite the connector | the edge opposite the connector | 连接器相对侧的边 | コネクタと反対側の辺 |
| connector side | connector side / socket side | 连接器侧 / 插座侧 | コネクタ側 / ソケット側 |
| sensor side | sensor-side edge | 传感器侧边 | センサー側の辺 |
| C-mount-facing side | the side facing the C-mount | 朝向 C-mount 的一侧 | Cマウントに向く面 |
| component side | component side of the PCB | 元件面 | 部品面 |
| solder side | solder side of the PCB | 焊接面 | はんだ面 |
| center aligned | centered / center-aligned | 居中 / 中心对齐 | 中央揃え / 中心合わせ |
| same axis | coaxial / on the same axis | 同轴 | 同軸 |
| same center | concentric | 同心 | 同心 |
| same plane | coplanar / in the same plane | 共面 | 同一平面 |
| flush surfaces | flush with each other | 齐平 | 面一（つらいち） |
| top/bottom are level | the bottom planes are coplanar | 底面共面 | 底面が同一平面 |

Useful grammar:

- Increase the clearance **by** `2 mm`.
- Set the diameter **to** `25.4 mm`.
- Move the pocket `2 mm` **toward** the sensor-side edge.
- Keep the sensor centered **on** the optical axis.
- Place the socket **on** the connector edge.
- Cut the relief **through to** the holder edge.
- Measure `7.5 mm` **from** the sensor-side short edge.

## Rephrasing Recent Design Requests

| Rough wording | Better English | 中文说明 | 日本語 |
| --- | --- | --- | --- |
| the C-mount is hang over | The C-mount side has an overhang. | C-mount 这一侧有悬垂/悬空。 | Cマウント側にオーバーハングがあります。 |
| make hanging part fill to ground | Add support-free geometry under the overhang, or remove the overhang. | 给悬垂下面补支撑结构，或去掉悬垂。 | オーバーハングの下を支える形状にする、またはオーバーハングをなくす。 |
| no middle cube | Remove the intermediate block; place the C-mount socket directly against the sensor plate. | 去掉中间连接块，让 C-mount 直接贴上传感器板座。 | 中間ブロックをなくし、Cマウントソケットをセンサープレートに直接接触させる。 |
| socket width parallel to long edge | the socket clearance in the long-edge direction | 插座沿 PCB 长边方向的避让宽度 | 長辺方向のソケット逃げ寸法 |
| make current clearance wider | Enlarge the socket relief by `2 mm` toward the sensor-side edge. | 把插座避让槽向传感器侧扩大 2 mm。 | ソケットの逃げをセンサー側へ 2 mm 広げる。 |
| install sensor deeper | Let the PCB slide deeper into the tray/pocket. | 让 PCB 更深地插入托槽。 | PCB がポケットの奥まで入るようにする。 |
| the screw cannot reach the hole | The far mounting holes do not line up because the PCB cannot seat deeply enough. | 因 PCB 没有插到底，远端安装孔对不上。 | PCB が奥まで入らないため、奥側の取付穴が合いません。 |
| add 0.1 each side | Add `0.1 mm` clearance on each side, symmetrically. | 每边对称增加 0.1 mm 间隙。 | 各側に 0.1 mm ずつ対称にクリアランスを追加する。 |
| add 0.4 mm in diameter | Increase the hole diameter by `0.4 mm`. | 孔径增加 0.4 mm。 | 穴径を 0.4 mm 大きくする。 |
| sink the PCB | Add a recessed pocket for the PCB. | 给 PCB 做沉槽/凹槽。 | PCB 用のポケット（凹み）を作る。 |
| LCD edge sink thickness | Add a shallow retaining ledge around the clear aperture. | 在通光孔周围做浅台阶承托 LCD。 | 透過開口の周囲に浅い受け段を作る。 |
| thread not go beyond cylinder | Bound the thread inside the cylinder length; do not let the teeth protrude past the end faces. | 螺纹限制在圆柱长度内，不要越过端面。 | ねじ山を円筒長さ内に収め、端面からはみ出させない。 |
| shell inside the thread | There are leftover internal sliver faces/shells inside the threaded bore. | 螺纹孔内有残留薄片面/壳。 | ねじ穴の内側に微小な残り面/シェルがあります。 |
| not clean / messy CAD | The B-rep is too messy to edit reliably. Please rebuild this region as clean geometry. | B-rep 面太乱，不便编辑；请重建该区域。 | B-rep が乱れて編集しにくいので、この部分をきれいな形状で再構築してください。 |

## Fit And Assembly Terms

| English | 中文 | 日本語 | Use |
| --- | --- | --- | --- |
| insert | 插入 | 挿入する / 差し込む | Smooth part into a hole or pocket. |
| slide into | 滑入 / 推入 | スライドして入れる | PCB, slide, or tray fit. |
| seat fully | 完全就位 / 坐到底 | 奥まで収まる / 着座する | Part reaches its final position. |
| screw into | 拧入 / 旋入 | ねじ込む | Threaded male into female. |
| mate with | 配合 / 对接 | 嵌合する / 組み合わせる | General male/female connection. |
| press-fit | 压入配合 | 圧入 | Tight interference fit. |
| slip fit | 间隙配合 / 滑配 | すきまばめ / スリップフィット | Easy removable fit. |
| clearance fit | 间隙配合 | すきまばめ | There is intentional extra space. |
| interference fit | 过盈配合 | しまりばめ | Part is intentionally oversized/tight. |
| locating peg | 定位柱 | 位置決めピン | Foot/peg used to align two parts. |
| matching hole | 定位孔 / 配合孔 | 位置決め穴 | Hole that receives a peg. |
| alignment feature | 定位结构 | 位置決め形状 | General positioning geometry. |
| latch / simple lock | 卡扣 / 简单锁扣 | ラッチ / 簡易ロック | Simple mechanical retention. |

Natural sentence:

> Screw the male C-mount thread into the female C-mount receiver until the two
> bottom planes are flush.

中文：

> 将公 C-mount 螺纹旋入母 C-mount 接口，直到两个底面齐平。

日本語：

> オスの Cマウントねじをメスの Cマウント受けにねじ込み、2つの底面が面一になるまで合わせる。

## Threads, Taps, And Printed Thread Language

| English | 中文 | 日本語 |
| --- | --- | --- |
| male thread / external thread | 公螺纹 / 外螺纹 | 雄ねじ / 外ねじ |
| female thread / internal thread | 母螺纹 / 内螺纹 | 雌ねじ / 内ねじ |
| threaded bore | 螺纹孔 | ねじ穴 / めねじ穴 |
| pilot hole / tap drill hole | 底孔 | 下穴 |
| tap | 丝锥 | タップ |
| die | 板牙 | ダイス |
| tap a hole | 攻丝 | タップを立てる |
| thread pitch | 螺距 | ピッチ |
| major diameter | 大径 / 标称大径 | 外径 / 呼び径 |
| minor diameter | 小径 / 牙底径 | 谷径 / 内径 |
| crest | 牙顶 | 山頂 |
| root | 牙根 | 谷底 |
| thread height | 牙高 | ねじ山高さ |
| lead-in chamfer | 导入倒角 | 入口面取り |
| runout | 退刀 / 末端过渡 | 逃げ / ねじ終端部 |
| thread engagement | 螺纹啮合长度 | ねじのかかり |
| thread cutter | 螺纹布尔切割体 | ねじ切りカッター |
| subtract the cutter | 减去切割体 / 布尔差集 | カッターを差し引く |

Thread spec examples:

- `1"-32 UNS tap`: standard C-mount tap, nominal `25.4 mm`, pitch
  `0.79375 mm`.
- `M30 x 0.75 tap`: metric `30 mm` nominal diameter, `0.75 mm` pitch.
- `M30 x 0.8 printed thread`: not a standard tap spec; it describes a
  3D-printed or CAD-modeled thread with `30 mm` nominal diameter and `0.8 mm`
  pitch.

Natural English:

> For the female receiver, start with a `25.0 mm` pilot bore and subtract a
> male-thread-shaped cutter whose crest diameter is `25.4 mm`.

中文：

> 对母接口，先做 `25.0 mm` 底孔，再减去一个牙顶直径为 `25.4 mm` 的公螺纹形状切割体。

日本語：

> メス側の受けは、まず `25.0 mm` の下穴を作り、山頂径 `25.4 mm` のオスねじ形状カッターを差し引きます。

## Pockets, Reliefs, Holes, And Cutouts

| English | 中文 | 日本語 | Meaning |
| --- | --- | --- | --- |
| pocket | 凹槽 / 容纳槽 | ポケット | Recess that holds a part. |
| recessed pocket | 沉槽 / 下沉槽 | 凹みポケット | Pocket below the surface. |
| recess | 凹陷 / 沉台 | 凹み / ザグリ | General lowered region. |
| relief / clearance relief | 避让 / 让位槽 | 逃げ / 逃げ加工 | Space for protrusions. |
| cutout | 开口 / 切口 | 切り欠き / 開口 | Removed area, often through. |
| through cut | 贯穿切除 | 貫通カット | Cut passes all the way through. |
| blind hole | 盲孔 | 止まり穴 | Hole does not go through. |
| through hole | 通孔 | 貫通穴 | Hole goes through. |
| clearance hole | 间隙孔 / 螺钉通孔 | クリアランス穴 | Screw passes through freely. |
| tapped hole | 螺纹孔 / 攻丝孔 | タップ穴 | Hole with internal thread. |
| counterbore | 沉孔 / 平底沉孔 | 座ぐり | Flat-bottom recess for screw head. |
| countersink | 锥形沉孔 | 皿ザグリ | Conical recess for flat-head screw. |
| ledge / retaining ledge | 承台 / 台阶边 | 受け段 / 支え段 | Shelf that supports a part. |
| shoulder | 肩部 / 台阶 | ショルダー / 段差 | Sudden diameter/height step. |

Good sentence for LCD/light valve:

> Make the center clear aperture a through-cut. Around it, add a `1 mm` wide
> retaining ledge recessed by the LCD thickness so the LCD sits on the ledge
> but the active area remains open.

中文：

> 中心通光孔做成贯穿开口；周围做 `1 mm` 宽、深度等于 LCD 厚度的承托台阶，让 LCD 坐在台阶上，但有效通光区域保持空。

日本語：

> 中央の有効開口は貫通カットにし、その周囲に LCD の厚み分だけ下げた幅 `1 mm` の受け段を作ります。LCD はその段に載り、有効領域は開いたままにします。

## PCB, Sensor, LED, And Connector Terms

| English | 中文 | 日本語 |
| --- | --- | --- |
| PCB | 电路板 / PCB | 基板 / PCB |
| board outline | 板框 / 外形 | 基板外形 |
| footprint | 封装 / 焊盘封装 | フットプリント |
| pad | 焊盘 | パッド |
| plated through hole / PTH | 金属化通孔 | スルーホール |
| mounting hole | 安装孔 | 取付穴 |
| pin pitch | 引脚间距 | ピンピッチ |
| pin header | 排针 | ピンヘッダ |
| socket / receptacle | 插座 / 母座 | ソケット / レセプタクル |
| right-angle header | 直角排针 | ライトアングルピンヘッダ |
| DuPont jumper wire | 杜邦线 | デュポン線 / ジャンパーワイヤ |
| solder joint | 焊点 | はんだ接合部 |
| protrusion | 凸出物 | 突起 |
| wire exit | 出线口 / 走线出口 | ケーブル出口 |
| connector clearance | 连接器避让 | コネクタ逃げ |

Good sentence for the TSL25911 problem:

> The XH2.54 socket relief is too short in the PCB long-edge direction. Please
> extend the relief `2 mm` toward the sensor-side edge so the board can slide
> deeper into the pocket and the far M2 holes line up.

中文：

> XH2.54 插座避让槽沿 PCB 长边方向不够长。请把避让槽向传感器侧延长 `2 mm`，这样板子可以更深插入凹槽，远端的 M2 孔也能对齐。

日本語：

> XH2.54 ソケットの逃げが、PCB の長辺方向に少し足りません。逃げをセンサー側へ `2 mm` 延ばして、基板がポケットの奥まで入り、奥側の M2 穴が合うようにしてください。

## Optical And Mechanical Holder Terms

| English | 中文 | 日本語 |
| --- | --- | --- |
| optical axis | 光轴 | 光軸 |
| clear aperture | 通光孔 / 有效孔径 | 有効開口 |
| active aperture | 有效通光区域 | 有効開口部 |
| C-mount receiver | C-mount 母接口 / 接收端 | Cマウント受け |
| C-mount adapter | C-mount 转接件 | Cマウントアダプタ |
| lens seat | 镜片座 / 镜片承台 | レンズ受け |
| lens holder | 镜片座 / 镜片支架 | レンズホルダー |
| cage system | 笼式光学结构 | ケージシステム |
| cage rod | 笼杆 / 光学杆 | ケージロッド |
| rod socket | 杆孔 / 杆座 | ロッド受け穴 |
| blind rod pocket | 不贯穿杆孔 | 止まりロッド穴 |
| sample holder | 样品架 | サンプルホルダー |
| slide holder | 载玻片架 | スライドガラスホルダー |
| Petri dish holder | 培养皿架 | シャーレホルダー |
| reflector holder | 反射镜座 / 反射片座 | 反射板ホルダー |
| light valve holder | 光阀支架 | 光バルブホルダー |

Natural cage-holder request:

> Make a two-piece cage sample holder. Each half is `30 mm` tall. Add four
> blind rod pockets for the standard cage rods on both the top and bottom
> halves. Keep the sample tray centered on the optical axis.

中文：

> 做一个上下两片式笼式样品架。每片高度 `30 mm`。上下两片都做四个不贯穿的笼杆孔。样品托槽保持在光轴中心。

日本語：

> 上下2分割のケージ用サンプルホルダーを作ります。各パーツの高さは `30 mm`。上下それぞれに標準ケージロッド用の止まり穴を4つ作り、サンプルトレイは光軸中心に合わせます。

## Printability And 3D Printing Words

| English | 中文 | 日本語 |
| --- | --- | --- |
| print tolerance | 打印公差 | 造形公差 |
| clearance | 间隙 / 余量 | クリアランス |
| shrinkage / printer error | 收缩 / 打印误差 | 収縮 / 造形誤差 |
| support material | 支撑材料 | サポート材 |
| support-free | 无需支撑 | サポート不要 |
| overhang | 悬垂 / 悬空 | オーバーハング |
| bridge | 桥接 | ブリッジ |
| wall thickness | 壁厚 | 肉厚 |
| minimum wall thickness | 最小壁厚 | 最小肉厚 |
| chamfer | 倒角 | 面取り |
| fillet | 圆角 | フィレット / R |
| roundover | 外圆角 | 丸め |
| print orientation | 打印方向 | 造形方向 |
| layer lines | 层纹 | 積層痕 |
| test coupon | 测试样块 | テストピース |

Useful prompt:

> Make this printable without supports. Avoid overhangs on the C-mount side,
> keep the wall thickness at least `3 mm`, and add `0.2 mm` radial clearance
> for printed slip-fit parts.

中文：

> 让这个设计无需支撑即可打印。避免 C-mount 一侧出现悬垂，壁厚至少 `3 mm`，滑配的打印件增加 `0.2 mm` 径向间隙。

日本語：

> サポートなしで印刷できる形にしてください。Cマウント側のオーバーハングを避け、肉厚は最低 `3 mm`、スリップフィット部には半径方向に `0.2 mm` のクリアランスを追加してください。

## CAD Operation Terms

| English | 中文 | 日本語 |
| --- | --- | --- |
| solid body | 实体 | ソリッドボディ |
| surface / shell | 曲面 / 壳 | サーフェス / シェル |
| B-rep | 边界表示 | B-rep / 境界表現 |
| sliver face | 细碎残面 | 微小な残り面 |
| internal face | 内部残面 | 内部面 |
| union | 布尔并集 | ブーリアン結合 |
| subtract / cut | 布尔差集 / 切除 | 差分 / カット |
| intersect | 布尔交集 | 交差 |
| trim | 修剪 | トリム |
| rebuild | 重建 | 再構築 |
| decouple | 解耦 / 分成独立体 | 分離する |
| multibody STEP | 多实体 STEP | マルチボディ STEP |
| assembly STEP | 装配 STEP | アセンブリ STEP |
| proxy body | 参考占位体 | プロキシ形状 |
| cutter body | 切割体 | カッター形状 |
| cutaway / section | 剖切图 | 断面 / カットモデル |
| exploded view | 爆炸图 | 分解図 |
| full-view render | 全视图渲染 | 全体レンダー |

Good sentence:

> Please export the final part as a clean multibody STEP: C-mount socket,
> sensor plate, thread cutter, board proxy, and assembly should be separate
> selectable bodies.

中文：

> 请导出干净的多实体 STEP：C-mount 接口、传感器板座、螺纹切割体、PCB 占位体和装配体都应是可单独选择的实体。

日本語：

> 最終パーツはきれいなマルチボディ STEP として出力してください。Cマウントソケット、センサープレート、ねじカッター、基板プロキシ、アセンブリを個別に選択できるボディにしてください。

## File Format Words

| Format | English use | 中文 | 日本語 |
| --- | --- | --- | --- |
| STEP / `.step` | Best for editable CAD exchange. | 最适合可编辑 CAD 交换 | 編集可能なCAD交換に最適 |
| Parasolid / `.x_t`, `.x_b` | Best if both CAD tools support it. | CAD 内核级交换，通常更干净 | CADカーネル間の交換に強い |
| Shapr3D / `.shapr` | Native Shapr3D project; may preserve bodies/history. | Shapr3D 原生文件 | Shapr3D ネイティブ |
| STL / `.stl` | Mesh for 3D printing, not good for editing. | 打印网格，不适合编辑 | 3Dプリント用メッシュ、編集には不向き |
| 3MF / `.3mf` | Better print package than STL; can store units/materials. | 打印包，可保存单位/材料 | 印刷用パッケージ |
| DXF / `.dxf` | 2D sketch/profile export. | 2D 草图/轮廓 | 2Dスケッチ |
| SVG / `.svg` | 2D drawing/vector diagram. | 矢量图 | ベクター図 |
| PDF | Drawing/report for checking. | 图纸/报告 | 図面/レポート |
| GLB/OBJ | Visual mesh/model sharing. | 可视化网格 | 表示用メッシュ |

Practical recommendation:

> For editing the part, export STEP or Parasolid. For printing only, export STL
> or 3MF. For sketches, export DXF or SVG. For checking dimensions, also export
> a PDF drawing.

中文：

> 如果要编辑零件，优先导出 STEP 或 Parasolid；只打印可导出 STL 或 3MF；草图导出 DXF 或 SVG；检查尺寸再导出 PDF 图纸。

日本語：

> 部品を編集するなら STEP または Parasolid、印刷だけなら STL または 3MF、スケッチは DXF または SVG、寸法確認には PDF 図面も出力します。

## Prompt Templates You Can Reuse

### Enlarge A Connector Clearance

```text
The connector relief is too short in the PCB long-edge direction. Please make a
new sibling design and enlarge the socket/wire relief by 2 mm toward the
sensor-side edge. Keep the optical axis, board pocket, C-mount thread, and
mounting-hole locations unchanged.
```

中文：

```text
连接器避让槽沿 PCB 长边方向不够长。请新建一个 sibling design，把插座/出线避让槽向传感器侧扩大 2 mm。光轴、PCB 槽、C-mount 螺纹和安装孔位置都不要改。
```

日本語：

```text
コネクタの逃げが PCB の長辺方向に足りません。新しい兄弟版デザインを作り、ソケット/ケーブル逃げをセンサー側へ 2 mm 広げてください。光軸、基板ポケット、Cマウントねじ、取付穴位置は変えないでください。
```

### Fix A Threaded Receiver

```text
The threaded receiver looks messy in CAD. Please do not fill over the old
thread. Trim away the old receiver at a stable datum, rebuild the receiver as
clean geometry, then cut the pilot bore and bounded thread cutter. Export the
thread cutter and final body separately.
```

中文：

```text
这个螺纹接口在 CAD 里看起来很乱。不要直接填充旧螺纹再重切。请在稳定基准面处切掉旧接口，重建干净的接口几何，再切底孔和受限的螺纹切割体。请分别导出螺纹切割体和最终实体。
```

日本語：

```text
このねじ受けは CAD 上で形状が乱れています。古いねじを埋めて再カットするのではなく、安定した基準面で古い受けを切り落とし、きれいな形状で受けを再構築してから、下穴と範囲を限定したねじカッターを差し引いてください。ねじカッターと最終ボディは別々に出力してください。
```

### Add A PCB Pocket

```text
Add a recessed PCB pocket with 0.2 mm clearance on each side. Keep the sensor
package centered on the optical axis. Add reliefs for solder joints, the pin
header, and the wire exit.
```

中文：

```text
增加一个 PCB 沉槽，每边留 0.2 mm 间隙。传感器封装保持在光轴中心。给焊点、排针和出线口增加避让。
```

日本語：

```text
PCB 用の凹みポケットを作り、各側に 0.2 mm のクリアランスを入れてください。センサーパッケージは光軸中心に合わせます。はんだ部、ピンヘッダ、ケーブル出口の逃げも追加してください。
```

### Make A Two-Piece Printed Holder

```text
Make this a two-piece printed holder. Use alignment pegs and matching holes:
make the pegs 0.2 mm smaller and the holes 0.2 mm larger for print tolerance.
The two halves should close flush and keep the sample centered on the optical
axis.
```

中文：

```text
把它做成两片式 3D 打印支架。使用定位柱和对应定位孔：定位柱缩小 0.2 mm，孔放大 0.2 mm 作为打印公差。两片合上后表面齐平，并保持样品在光轴中心。
```

日本語：

```text
これを2分割の3Dプリントホルダーにしてください。位置決めピンと対応する穴を使い、印刷公差としてピンは 0.2 mm 小さく、穴は 0.2 mm 大きくします。2つの部品を閉じたとき面一になり、サンプルは光軸中心に保ってください。
```

## Quick Word Choices

- Use **relief** for space removed to avoid a connector, wire, solder joint, or
  protrusion.
- Use **pocket** for a recess that holds a board, LCD, slide, Petri dish, or
  sensor module.
- Use **ledge** or **shoulder** for a small shelf that supports a part.
- Use **overhang** when material hangs beyond an edge and may need print
  support.
- Use **flush** when two surfaces are level.
- Use **coplanar** when two planes are mathematically in the same plane.
- Use **coaxial** for cylinders/bores sharing one axis.
- Use **concentric** for circles sharing one center.
- Use **screw into** for threads.
- Use **insert into** or **slide into** for smooth holes/pockets.
- Use **mate with** for general male/female assembly.
- Use **tap** for cutting internal threads with a tool.
- Use **pilot hole** or **tap drill hole** for the hole made before tapping.
