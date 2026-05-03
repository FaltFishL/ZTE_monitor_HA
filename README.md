# ZTE Monitor HA

全面的 ZTE 路由器 Home Assistant 集成——设备追踪、WiFi 配置、WAN 状态、Mesh 拓扑、ACL 规则。

## 功能

- 在线设备实时追踪（含品牌/型号/RSSI/MLO 信息）
- WiFi 主网络和访客网络配置
- WAN 连接状态（IPv4/IPv6）
- Mesh 组网拓扑
- ACL 规则列表
- NTP 时间信息
- 路由器硬件详情
- 远程重启路由器
- 暂停/恢复扫描

## 安装（HACS 自定义仓库）

1. HACS → 集成 → 右上角 ⋮ → 自定义仓库
2. 仓库地址：`https://github.com/FaltFishL/ZTE_monitor_HA`
3. 类别：Integration
4. 搜索 "ZTE Monitor HA" → 下载 → 重启 Home Assistant

## 支持的型号

- ZTE ZXSLC SR7410（BE7200 Pro+）
- ZTE ZXSLC SR1010（星云Max）
- 其他基于 Vue.js 接口的新款 ZTE 路由器
