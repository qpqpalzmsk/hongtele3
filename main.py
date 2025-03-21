import os
import asyncio
import time
import random
from telethon import TelegramClient, events, functions
from telethon.errors import FloodWaitError, RPCError

##################################
# [1] 텔레그램 기본 설정
##################################
API_ID = int(os.getenv("API_ID", "22302046"))
API_HASH = os.getenv("API_HASH", "bf53409eb9fbb23b5b66e01aead9e78d")
PHONE_NUMBER = os.getenv("PHONE_NUMBER", "+998331107364")

SESSION_NAME = "my_telethon_session"
client = TelegramClient(
    SESSION_NAME,
    API_ID,
    API_HASH,
    timeout=60,
    auto_reconnect=True
)

##################################
# [2] 광고(홍보) 계정 & 메시지 설정
##################################
MARKETING_USER = "@cuz_z"  # 홍보 계정 유저네임(or ID)
MSG_LIMIT = 3  # 최근 메시지 3개 (a, b, c) 로 라운드 로빈

##################################
# [3] 그룹/전송 파라미터 (고정 시간)
##################################
MAX_GROUPS = 20       # 20개 그룹
BATCH_SIZE = 5        # 배치당 5개 그룹

DELAY_GROUP = random.randint(120, 180)       # 그룹 간 45초
DELAY_BATCH = random.randint(600, 1200)      # 배치 간 10분(600초)
DELAY_CYCLE = random.randint(3600, 5400)     # 사이클 간 102분(6120초)

##################################
# [4] 연결/세션 확인 함수
##################################
async def ensure_connected():
    if not client.is_connected():
        print("[INFO] Telethon is disconnected. Reconnecting...")
        await client.connect()

    if not await client.is_user_authorized():
        print("[WARN] 세션 없음/만료 → OTP 로그인 시도")
        await client.start(phone=PHONE_NUMBER)
        print("[INFO] 로그인/재인증 완료")

##################################
# [4-1] keep_alive 함수 추가!
##################################
async def keep_alive():
    """
    10분마다 호출해서 Telethon 연결 상태를 확인하는 간단한 API 요청
    """
    try:
        await ensure_connected()
        await client(functions.help.GetNearestDcRequest())
        print("[INFO] keep_alive ping success")
    except Exception as e:
        print(f"[ERROR] keep_alive ping fail: {e}")

##################################
# [5] "복사+붙여넣기" 방식 전송 함수
##################################
async def copy_paste_message(dest, msg):
    try:
        if msg.media:
            caption_text = msg.message or ""
            await client.send_file(dest, msg.media, caption=caption_text)
        else:
            await client.send_message(dest, msg.message)
    except FloodWaitError as fw:
        print(f"[ERROR] FloodWait {fw.seconds}초. 대기 후 재시도.")
        await asyncio.sleep(fw.seconds + 5)
        if msg.media:
            caption_text = msg.message or ""
            await client.send_file(dest, msg.media, caption=caption_text)
        else:
            await client.send_message(dest, msg.message)

##################################
# [6] 메시지/그룹 로드
##################################
async def get_recent_marketing_msgs():
    await ensure_connected()
    msgs = await client.get_messages(MARKETING_USER, limit=MSG_LIMIT)
    return msgs

async def load_groups():
    await ensure_connected()
    dialogs = await client.get_dialogs()
    group_list = [d.id for d in dialogs if d.is_group or d.is_channel]
    return group_list[:MAX_GROUPS]

##################################
# [7] 1사이클(20개 그룹) 전송 로직
##################################
async def run_one_cycle(cycle_number: int):
    marketing_msgs = await get_recent_marketing_msgs()
    if not marketing_msgs:
        print("[WARN] 홍보 메시지를 불러오지 못함. 5분 대기 후 재시도.")
        await asyncio.sleep(300)
        return

    print(f"[INFO] 사이클 {cycle_number}/10 시작. 메시지 {len(marketing_msgs)}개")
    msg_idx = 0

    group_list = await load_groups()
    if not group_list:
        print("[WARN] 그룹 0개. 5분 대기 후 재시도.")
        await asyncio.sleep(300)
        return

    if len(group_list) < 20:
        print(f"[INFO] 실제 대상 그룹: {len(group_list)}개 < 20개")
    random.shuffle(group_list)

    batch_count = (len(group_list) + BATCH_SIZE - 1) // BATCH_SIZE
    for b_idx in range(batch_count):
        start_idx = b_idx * BATCH_SIZE
        end_idx = min(start_idx + BATCH_SIZE, len(group_list))
        batch = group_list[start_idx:end_idx]
        if not batch:
            break

        print(f"[INFO] 배치 {b_idx+1}/{batch_count}, 그룹 {start_idx}~{end_idx-1}")

        for g_idx, grp_id in enumerate(batch):
            current_msg = marketing_msgs[msg_idx]
            try:
                await copy_paste_message(grp_id, current_msg)
                print(f"[INFO] 복사 전송 성공 → group={grp_id}, msg_idx={msg_idx}")
            except RPCError as e:
                print(f"[ERROR] RPCError(chat_id={grp_id}): {e}")
            except Exception as e:
                print(f"[ERROR] 전송 실패(chat_id={grp_id}): {e}")

            msg_idx = (msg_idx + 1) % len(marketing_msgs)

            if g_idx < len(batch)-1:
                await asyncio.sleep(DELAY_GROUP)

        if b_idx < batch_count - 1:
            print(f"[INFO] 배치 {b_idx+1} 완료 → {DELAY_BATCH//60}분 대기.")
            await asyncio.sleep(DELAY_BATCH)

    print(f"[INFO] 사이클 {cycle_number}/10 끝. {DELAY_CYCLE//60}분 대기 후 다음 사이클.")
    await asyncio.sleep(DELAY_CYCLE)

##################################
# [8] 메인 루프
##################################
async def run_daily_cycles():
    cycle_num = 1
    while True:
        if cycle_num > 10:
            cycle_num = 1
            print("[INFO] 하루(10사이클) 완료 → 다음 날 사이클 재시작.")

        await run_one_cycle(cycle_num)
        cycle_num += 1

async def main():
    await client.connect()
    print("[INFO] client.connect() 완료")

    if not (await client.is_user_authorized()):
        print("[INFO] 세션 없음/만료 → OTP 로그인 시도")
        await client.start(phone=PHONE_NUMBER)
        print("[INFO] 로그인/재인증 성공")
    else:
        print("[INFO] 이미 인증된 세션 (OTP 불필요)")

    @client.on(events.NewMessage(pattern="/ping"))
    async def ping_handler(event):
        await event.respond("pong!")

    print("[INFO] 텔레그램 로그인(세션) 준비 완료")

    async def keep_alive_loop():
        while True:
            await keep_alive()
            await asyncio.sleep(600)  # 10분

    await asyncio.gather(
        run_daily_cycles(),
        keep_alive_loop()
    )

if __name__ == "__main__":
    asyncio.run(main())