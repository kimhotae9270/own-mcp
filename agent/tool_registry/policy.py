# agent/tool_registry/policy.py

# 전역 ReAct에서 노출하지 않을 태그/툴
REACT_EXCLUDE_TAGS = {"calendar"}  # 나중에 "drive" 추가 가능
REACT_EXCLUDE_TOOLS = set()          # 필요하면 name 단위로 추가

# 캘린더 에이전트/드라이브 에이전트는 별도 정책 가능
CALENDAR_AGENT_EXCLUDE_TAGS = []
DRIVE_AGENT_EXCLUDE_TAGS = []