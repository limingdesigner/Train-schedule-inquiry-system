import sqlite3
from datetime import datetime, timedelta

DB_FILE = 'trains.db'

# 初始化数据库（仅完善表结构：唯一约束、检查约束、索引、级联删除触发器）
def init_db():
    try:
        print("初始化数据库...")
        conn = sqlite3.connect(DB_FILE)
        # 开启外键（当前连接有效），以便新库中ON DELETE CASCADE生效
        conn.execute("PRAGMA foreign_keys = ON")
        cursor = conn.cursor()

        # 新库的表结构：加入CHECK约束，字段默认值等
        cursor.executescript('''
        -- 车次表
        CREATE TABLE IF NOT EXISTS trains (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            train_no TEXT NOT NULL,
            train_type TEXT NOT NULL
        );

        -- 停靠表
        CREATE TABLE IF NOT EXISTS stops (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            train_id INTEGER NOT NULL,
            station_name TEXT NOT NULL,
            departure_time TEXT,      -- 出发时间（终到站可为空）
            stop_duration INTEGER NOT NULL DEFAULT 0 CHECK (stop_duration >= 0),
            station_order INTEGER NOT NULL CHECK (station_order > 0),
            FOREIGN KEY (train_id) REFERENCES trains (id) ON DELETE CASCADE ON UPDATE CASCADE
        );

        -- 查询优化索引
        CREATE INDEX IF NOT EXISTS idx_stops_station_name ON stops (station_name);
        ''')

        # 兼容旧库：补全唯一性约束（用唯一索引实现），避免重复数据
        cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_trains_train_no_unique ON trains(train_no)')
        cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_stops_train_order_unique ON stops(train_id, station_order)')
        cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_stops_train_station_unique ON stops(train_id, station_name)')

        # 级联删除触发器：在未启用外键的连接上也可保障删除一致性
        cursor.executescript('''
        CREATE TRIGGER IF NOT EXISTS trg_trains_delete_cascade
        AFTER DELETE ON trains
        BEGIN
            DELETE FROM stops WHERE train_id = OLD.id;
        END;
        ''')

        conn.commit()
        conn.close()
        print("数据库初始化成功！")
    except Exception as e:
        print(f"数据库初始化失败: {e}")

# 功能1：添加车次
def add_train():
    try:
        print("开始添加车次信息...")
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        train_no = input("输入车次号: ").strip()
        train_type = input("输入列车型号: ").strip()

        cursor.execute("INSERT INTO trains (train_no, train_type) VALUES (?, ?)",
                       (train_no, train_type))
        train_id = cursor.lastrowid

        print("开始输入沿途停靠站（按顺序）。站名为空时结束录入：")
        order = 1
        while True:
            station = input(f"第{order}站名称 (空回车结束): ").strip()
            if not station:
                break
            departure = input("出发时间 (HH:MM): ").strip()
            stop_min_str = input("停靠分钟数 (整数): ").strip()
            stop_min = int(stop_min_str) if stop_min_str.isdigit() else 0

            cursor.execute('''
                INSERT INTO stops (train_id, station_name, departure_time, stop_duration, station_order)
                VALUES (?, ?, ?, ?, ?)
            ''', (train_id, station, departure, stop_min, order))
            order += 1

        conn.commit()
        conn.close()
        print("车次信息录入完成！\n")
    except Exception as e:
        print(f"添加车次失败: {e}")

# 计算时间差（考虑跨天情况）
def calculate_duration(departure_time, arrival_time):
    """
    计算两个时间字符串之间的时长
    :param departure_time: 出发时间字符串 (HH:MM)
    :param arrival_time: 到达时间字符串 (HH:MM)
    :return: 时长字符串 (X小时Y分钟)
    """
    try:
        # 处理空值或None的情况
        if not departure_time or not arrival_time:
            return "时间信息不完整"
        
        # 清理时间字符串（去除空格）
        departure_time = departure_time.strip()
        arrival_time = arrival_time.strip()
        
        # 尝试多种时间格式
        for fmt in ["%H:%M", "%H:%M:%S", "%H.%M"]:
            try:
                dep_time = datetime.strptime(departure_time, fmt)
                arr_time = datetime.strptime(arrival_time, fmt)
                break
            except ValueError:
                continue
        else:
            # 如果都不匹配，尝试手动处理
            if ":" in departure_time and ":" in arrival_time:
                dep_parts = departure_time.split(":")
                arr_parts = arrival_time.split(":")
                
                dep_hour = int(dep_parts[0])
                dep_minute = int(dep_parts[1])
                arr_hour = int(arr_parts[0])
                arr_minute = int(arr_parts[1])
                
                dep_time = datetime.strptime(f"{dep_hour:02d}:{dep_minute:02d}", "%H:%M")
                arr_time = datetime.strptime(f"{arr_hour:02d}:{arr_minute:02d}", "%H:%M")
            else:
                return f"时间格式错误"
        
        # 计算时间差
        if arr_time < dep_time:
            # 如果到达时间小于出发时间，说明跨天了
            arr_time += timedelta(days=1)
        
        duration = arr_time - dep_time
        
        # 转换为小时和分钟
        total_minutes = int(duration.total_seconds() / 60)
        hours = total_minutes // 60
        minutes = total_minutes % 60
        
        if hours > 0:
            return f"{hours}小时{minutes}分钟"
        else:
            return f"{minutes}分钟"
            
    except Exception as e:
        return "无法计算"

# 功能2：查询车次（增加计算用时功能）
def query_trains():
    try:
        print("开始查询车次...")
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        start = input("输入出发站: ").strip()
        end = input("输入到达站: ").strip()

        cursor.execute('''
            SELECT t.train_no, t.train_type, s1.departure_time, s2.departure_time
            FROM trains t
            JOIN stops s1 ON t.id = s1.train_id
            JOIN stops s2 ON t.id = s2.train_id
            WHERE s1.station_name=? AND s2.station_name=? AND s1.station_order < s2.station_order
            ORDER BY s1.departure_time
        ''', (start, end))
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            print("没有符合条件的车次。\n")
        else:
            print("\n" + "="*90)
            print("符合条件的车次：")
            print("="*90)
            print(f"{'车次':<10} {'型号':<10} {'出发时间':<15} {'到达时间':<15} {'用时':<20}")
            print("-"*90)
            
            for r in rows:
                train_no = r[0] if r[0] else "未知"
                train_type = r[1] if r[1] else "未知"
                departure_time = r[2] if r[2] else "未知"
                arrival_time = r[3] if r[3] else "未知"
                
                # 计算用时
                if departure_time != "未知" and arrival_time != "未知":
                    duration = calculate_duration(departure_time, arrival_time)
                else:
                    duration = "时间信息不完整"
                
                print(f"{train_no:<10} {train_type:<10} {departure_time:<15} {arrival_time:<15} {duration:<20}")
            
            print("="*90)
            print()
    except Exception as e:
        print(f"查询车次失败: {e}")

# 功能3：搜索车次号显示详细信息
def search_train():
    try:
        print("搜索车次详细信息...")
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        train_no = input("请输入要搜索的车次号: ").strip()
        
        # 查询车次基本信息
        cursor.execute('''
            SELECT id, train_no, train_type FROM trains WHERE train_no = ?
        ''', (train_no,))
        train = cursor.fetchone()
        
        if not train:
            print(f"未找到车次号为 '{train_no}' 的车次。\n")
            conn.close()
            return
        
        train_id = train[0]
        
        # 查询该车次的所有站点信息
        cursor.execute('''
            SELECT station_name, departure_time, stop_duration, station_order
            FROM stops 
            WHERE train_id = ? 
            ORDER BY station_order
        ''', (train_id,))
        stops = cursor.fetchall()
        
        conn.close()
        
        # 显示车次详细信息
        print("\n" + "="*80)
        print(f"车次详细信息")
        print("="*80)
        print(f"车次号: {train[1]}")
        print(f"列车型号: {train[2]}")
        print(f"途经站点数: {len(stops)}")
        
        if stops:
            # 计算全程用时
            first_station = stops[0]
            last_station = stops[-1]
            
            if first_station[1] and last_station[1]:
                total_duration = calculate_duration(first_station[1], last_station[1])
                print(f"全程用时: {total_duration}")
            
            print(f"始发站: {first_station[0]} ({first_station[1] if first_station[1] else '未设置时间'})")
            print(f"终点站: {last_station[0]} ({last_station[1] if last_station[1] else '未设置时间'})")
            
            print("\n" + "-"*80)
            print("沿途停靠站点：")
            print("-"*80)
            print(f"{'序号':<6} {'站名':<15} {'到达/出发时间':<12} {'停靠时间':<10} {'区间用时':<15}")
            print("-"*80)
            
            prev_time = None
            for idx, stop in enumerate(stops, start=1):
                station_name = stop[0]
                departure_time = stop[1] if stop[1] else "---"
                stop_duration = f"{stop[2]}分钟" if stop[2] > 0 else "---"
                
                # 计算区间用时
                interval_duration = "---"
                if prev_time and stop[1]:
                    interval_duration = calculate_duration(prev_time, stop[1])
                
                # 对于第一站，区间用时显示为"始发站"
                if idx == 1:
                    interval_duration = "始发站"
                # 对于最后一站，如果没有出发时间，显示为"终点站"
                elif idx == len(stops) and not stop[1]:
                    interval_duration = "终点站"
                    departure_time = "终点站"
                
                print(f"{idx:<6} {station_name:<15} {departure_time:<12} {stop_duration:<10} {interval_duration:<15}")
                
                if stop[1]:
                    prev_time = stop[1]
            
            # 统计信息
            print("\n" + "-"*80)
            total_stop_time = sum(stop[2] for stop in stops if stop[2])
            print(f"总停靠时间: {total_stop_time} 分钟")
            
            # 计算平均停站时间（排除始发站和终点站）
            if len(stops) > 2:
                middle_stops = stops[1:-1]
                avg_stop_time = sum(stop[2] for stop in middle_stops) / len(middle_stops) if middle_stops else 0
                print(f"平均停站时间: {avg_stop_time:.1f} 分钟（不含始发和终点站）")
        else:
            print("该车次没有站点信息。")
        
        print("="*80)
        print()
        
    except Exception as e:
        print(f"搜索车次失败: {e}")

# 功能4：查看所有车次数据
def view_all_trains():
    try:
        print("查看所有车次数据...")
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT t.train_no, t.train_type, s.station_name, s.departure_time, s.stop_duration, s.station_order
            FROM trains t
            JOIN stops s ON t.id = s.train_id
            ORDER BY t.train_no, s.station_order
        ''')
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            print("暂无车次信息。\n")
        else:
            print("所有车次信息：")
            current_train_no = None
            first_station_time = None
            stations_info = []
            
            for row in rows:
                if row[0] != current_train_no:
                    # 如果不是第一个车次，显示上一个车次的总用时
                    if current_train_no and len(stations_info) >= 2:
                        first_time = stations_info[0][3]
                        last_time = stations_info[-1][3]
                        if first_time and last_time:
                            total_duration = calculate_duration(first_time, last_time)
                            print(f"  【全程用时: {total_duration}】")
                    
                    print(f"\n车次号: {row[0]} | 车型: {row[1]}")
                    current_train_no = row[0]
                    stations_info = []
                
                print(f"  站名: {row[2]} | 出发时间: {row[3] if row[3] else '终点站'} | 停靠时间: {row[4]} 分钟")
                stations_info.append(row)
            
            # 显示最后一个车次的总用时
            if current_train_no and len(stations_info) >= 2:
                first_time = stations_info[0][3]
                last_time = stations_info[-1][3]
                if first_time and last_time:
                    total_duration = calculate_duration(first_time, last_time)
                    print(f"  【全程用时: {total_duration}】")
            
            print()
    except Exception as e:
        print(f"查看所有车次数据失败: {e}")

# 功能5：删除车次
def delete_train():
    try:
        print("开始删除车次...")
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        train_no = input("请输入车次号以删除: ").strip()

        cursor.execute('''
            SELECT id FROM trains WHERE train_no = ?
        ''', (train_no,))
        train = cursor.fetchone()

        if not train:
            print("车次号不存在。\n")
            conn.close()
            return

        # 显示将要删除的车次信息
        cursor.execute('''
            SELECT COUNT(*) FROM stops WHERE train_id = ?
        ''', (train[0],))
        stop_count = cursor.fetchone()[0]
        
        confirm = input(f"确认删除车次 '{train_no}'（包含 {stop_count} 个站点）? (y/n): ").strip().lower()
        
        if confirm == 'y':
            cursor.execute('DELETE FROM stops WHERE train_id = ?', (train[0],))
            cursor.execute('DELETE FROM trains WHERE id = ?', (train[0],))
            conn.commit()
            print("车次已删除。\n")
        else:
            print("取消删除操作。\n")

        conn.close()
    except Exception as e:
        print(f"删除车次失败: {e}")

# 主程序入口
def main():
    init_db()
    while True:
        print("========== 火车班次查询系统 ==========")
        print("1. 添加车次信息")
        print("2. 查询车次（按站点）")
        print("3. 搜索车次（按车次号）")
        print("4. 查看所有车次")
        print("5. 删除车次")
        print("6. 退出系统")
        choice = input("请选择操作: ").strip()

        if choice == '1':
            add_train()
        elif choice == '2':
            query_trains()
        elif choice == '3':
            search_train()
        elif choice == '4':
            view_all_trains()
        elif choice == '5':
            delete_train()
        elif choice == '6':
            print("程序已退出。")
            break
        else:
            print("输入无效，请重新选择。")

if __name__ == "__main__":
    main()