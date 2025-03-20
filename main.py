import os
import asyncio
import random
import time

from telethon import TelegramClient, events, functions
from telethon.errors import FloodWaitError, RPCError

# ========== [1] 텔레그램 API 설정 ==========
API_ID = int(os.getenv("API_ID", "21648534"))
API_HASH = os.getenv("API_HASH", "adb09882f9a7a28bd4798b3dc6385a0b")
PHONE_NUMBER = os.getenv("PHONE_NUMBER", "+818089299015")  # 예시

SESSION_NAME = "my_telethon_session"
client = TelegramClient(
    SESSION_NAME,
    API_ID,
    API_HASH,
    timeout=60,
    auto_reconnect=True
)

# ========== [2] 홍보(마케팅) 계정 ==========
MARKETING_USER = "@cuz_z"  # 유저네임 or 정수 ID

# ========== [3] 연결/세션 확인 함수 ==========
async def ensure_connected():
    if not client.is_connected():
        print("[INFO] Telethon is disconnected. Reconnecting...")
        await client.connect()

    if not await client.is_user_authorized():
        print("[WARN] 세션 없음/만료 → OTP 로그인 시도")
        await client.start(phone=PHONE_NUMBER)
        print("[INFO] 재로그인(OTP) 완료")

# ========== [4] keep_alive (연결 유지) ==========
async def keep_alive():
    """
    주기적으로(10분 등) 호출해서 Telethon 연결 상태 유지
    """
    try:
        await ensure_connected()
        await client(functions.help.GetNearestDcRequest())
        print("[INFO] keep_alive ping success")
    except Exception as e:
        print(f"[ERROR] keep_alive ping fail: {e}")

# ========== [5] 가입된 그룹/채널 목록 불러오기 ==========
async def load_all_groups():
    """
    내 계정이 가입한 모든 그룹(슈퍼그룹/채널 포함) ID 리스트
    """
    await ensure_connected()
    dialogs = await client.get_dialogs()
    return [d.id for d in dialogs if (d.is_group or d.is_channel)]

# ========== [6] '홍보 계정'의 최근 N개 메시지 가져오기 ==========
async def get_recent_messages(user, limit=9):
    """
    user(홍보 계정)에서 '최근 limit개' 메시지를 가져옴
    """
    await ensure_connected()
    msgs = await client.get_messages(user, limit=limit)
    # msgs[0]가 가장 최근 메시지
    return msgs  # 리스트(메시지 객체들)

# ========== [7] 메시지 3개를 그룹마다 순환(라운드 로빈)하여 전달 + 스팸 방지 대기 ==========
async def forward_ad_messages():
    """
    1) 홍보 계정에서 최근 3개 메시지를 가져옴
    2) 가입된 모든 그룹에 대해,
       - 메시지 3개를 순환하면서 Forward
       - 각 그룹 간 30~60초 대기
       - 5개 그룹마다 10~20분 대기
    3) 전체 그룹 한 사이클 끝나면 40~60분 대기
    4) 무한 반복
    """

    while True:  # 무한 루프
        try:
            await ensure_connected()

            # (A) 홍보 계정에서 메시지 3개 가져오기
            marketing_msgs = await get_recent_messages(MARKETING_USER, limit=9)
            if not marketing_msgs:
                print("[WARN] 홍보 계정에서 메시지를 가져오지 못했습니다. 10분 후 재시도.")
                await asyncio.sleep(600)
                continue

            # 혹시 실제로는 1~2개만 있으면, 있는 만큼만 사용
            num_msgs = len(marketing_msgs)
            print(f"[INFO] 홍보 메시지 {num_msgs}개 확보.")

            # (B) 모든 그룹 불러오기
            group_list = await load_all_groups()
            if not group_list:
                print("[WARN] 가입된 그룹이 없습니다. 10분 후 재시도.")
                await asyncio.sleep(600)
                continue

            print(f"[INFO] 이번 사이클: {len(group_list)}개 그룹에 전송을 시도합니다.")

            # (C) 그룹에 순차 전달(라운드 로빈)
            msg_idx = 0  # 메시지 선택 인덱스 (0→1→2→0→1→2→...)
            group_count = len(group_list)

            for i, grp_id in enumerate(group_list, start=1):
                current_msg = marketing_msgs[msg_idx]

                # Forward
                try:
                    await client.forward_messages(
                        entity=grp_id,
                        messages=current_msg.id,
                        from_peer=current_msg.sender_id
                    )
                    print(f"[INFO] 그룹 {i}/{group_count}에 메시지 {msg_idx} 전송 성공 → {grp_id}")
                except FloodWaitError as fwerr:
                    print(f"[ERROR] FloodWait: {fwerr}. {fwerr.seconds}초 대기 후 재시도.")
                    await asyncio.sleep(fwerr.seconds + 5)
                    # 재시도
                    try:
                        await client.forward_messages(
                            entity=grp_id,
                            messages=current_msg.id,
                            from_peer=current_msg.sender_id
                        )
                    except Exception as e2:
                        print(f"[ERROR] 재시도 실패(chat_id={grp_id}): {e2}")
                except RPCError as e:
                    print(f"[ERROR] Forward RPCError(chat_id={grp_id}): {e}")
                except Exception as e:
                    print(f"[ERROR] Forward 실패(chat_id={grp_id}): {e}")

                # (C-1) 메시지 인덱스 순환
                msg_idx = (msg_idx + 1) % num_msgs

                # (C-2) 5개 그룹마다 10~20분 대기
                if i % 5 == 0:
                    delay_batch = random.randint(600, 1200)  # 600=10분, 1200=20분
                    print(f"[INFO] {i}번째 그룹 전송 완료. {delay_batch//60}분 대기 후 다음 5개 진행.")
                    await asyncio.sleep(delay_batch)
                else:
                    # (C-3) 그 외(그룹 간) 30~60초 대기
                    delay_small = random.randint(30, 60)
                    print(f"[INFO] 다음 그룹 전송까지 {delay_small}초 대기...")
                    await asyncio.sleep(delay_small)

            # (D) 모든 그룹 전송(1 사이클) 끝나면 40~60분 대기
            rest_time = random.randint(2400, 3600)  # 40~60분
            print(f"[INFO] 전체 {group_count}개 그룹 전송 완료. {rest_time//60}분 후 다음 사이클.")
            await asyncio.sleep(rest_time)

        except Exception as e:
            print(f"[ERROR] forward_ad_messages() 전체 에러: {e}")
            print("[INFO] 10분 후 재시도.")
            await asyncio.sleep(600)


# ========== [8] 메인 함수 ==========
async def main():
    # (1) 텔레그램 연결
    await client.connect()
    print("[INFO] client.connect() 완료")

    # (2) 세션 인증 체크
    if not (await client.is_user_authorized()):
        print("[INFO] 세션 없음 or 만료 → OTP 로그인 시도")
        await client.start(phone=PHONE_NUMBER)
        print("[INFO] 첫 로그인 or 재인증 성공")
    else:
        print("[INFO] 이미 인증된 세션 (OTP 불필요)")

    @client.on(events.NewMessage(pattern="/ping"))
    async def ping_handler(event):
        await event.respond("pong!")

    print("[INFO] 텔레그램 로그인(세션) 준비 완료")

    # (A) keep_alive(10분 간격) + (B) 메시지 전송 루프 병행
    async def keep_alive_scheduler():
        while True:
            await keep_alive()
            await asyncio.sleep(600)  # 10분

    await asyncio.gather(
        forward_ad_messages(),
        keep_alive_scheduler()
    )

# ========== [9] 실행 ==========
if __name__ == "__main__":
    asyncio.run(main())