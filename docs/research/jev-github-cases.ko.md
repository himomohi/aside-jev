[English](jev-github-cases.md) | [한국어](jev-github-cases.ko.md)

# GitHub Jev 사용 사례와 구조 분석

조사일: 2026-10-05. 제안의 핵심은 **목표·제약·요소 간 관계·진행 이력을 보존한
작업 상태를 Jev에 전달하고, 필요한 맥락 판단을 한 요청에서 받는 구조**입니다.
DOM 요소나 사실을 하나씩 따로 평가하는 구조를 제안하지 않습니다. 현재 API는
여러 타입을 지원하지만 브라우저 경로는 줄 단위로 압축한 관찰과 행동 Choice를
사용하고, 의미 기반 최종 평가는 끝에 수행합니다. 작업 상태 표현과 호출 단위를
함께 바꾸자는 제안입니다.
[구조 변경 제안서](../rfcs/0001-composable-jev-decisions.ko.md).

## 조사 범위

GitHub에서 `jev typesafe`, `typesafe-ai`, 공식 조직의 저장소를 검색하고 Exa로
기본 타입·라우팅/평가·공식 예제의 세 방향에서 후보 30개를 요청했습니다.
중복과 무관한 결과를 제외한 뒤 **8개 GitHub 저장소의 원문 코드**를 확인했습니다.
사용 코드 사례 7개와 공식 설계 지침 1개이며 전체 생태계의 전수조사는 아닙니다.

[source manifest](jev-github-sources.json)에 커밋·파일·행 범위·근거 종류를 기록했습니다.
외부 프로젝트 실행, 유료 API 호출, 운영 배포 확인, 성능 수치 재현은 수행하지
않았습니다. 공식 샘플·평가 구현·커뮤니티 통합은 서로 다른 근거입니다.
`awesome-*` 목록과 검색용 요약 페이지는 발견용으로만 사용했고, 이름이 같은
다른 JEV 프로젝트나 TypeSafe API를 사용하지 않는 대체 모델은 제외했습니다.
공식 라이브 문서도 확인했지만 해당 웹 문서는 고정 버전이 아닙니다.

## 확인한 사례

| 출처 / 근거 종류 | 실제 코드 동작 | 적용할 점 |
| :--- | :--- | :--- |
| [TypeSafe Python SDK](https://github.com/typesafe-ai/typesafe-sdk-python/blob/f078f1e208a0d885154dc758344ae4fce77ac168/README.md#L17-L33) / 공식 샘플 | 지원 티켓을 정해진 카테고리에서 고르고 미해당 옵션을 둡니다. | 판단 하나면 충분할 때 단일 Choice는 유효합니다. |
| [WorkflowEvals](https://github.com/typesafe-ai/WorkflowEvals/blob/0ac3b8ad845429f0d8e064ecfb2430a47c5a25cb/evals/invoice_processing/structured/semantic.py#L46-L75) / 공식 평가 구현 | 의미 판단을 신호로 보존하고, 별도 코드가 정확한 사실·정책과 조합합니다. | 관찰·판단·정책을 분리합니다. |
| [공식 n8n 통합](https://github.com/typesafe-ai/n8n-nodes-typesafe-ai/blob/c12537bbd9ed7159b7bbe23678ca128c7b2fb52b/nodes/TypeSafeAi/TypeSafeAi.node.ts#L98-L150) / 워크플로 통합 | Choice confidence, Noul 참/거짓 경계와 불확실 분기, Score 단계별 라우팅을 구분합니다. | 모든 숫자를 같은 신뢰도로 취급하지 않습니다. |
| [jev-browser](https://github.com/jkudish/jev-browser/blob/1f0726cc8bc4483b96439504b594a01596d8e347/src/questions.ts#L6-L27) / 커뮤니티 브라우저 구현 | 행동 Choice·완료 Noul·정체 Noul을 같은 상태에서 묻고 실행 전에 중단 조건을 검사합니다. | 독립적인 단계 판단을 묶고 실행 전에 조합합니다. |
| [pi-jev-skill-picker](https://github.com/safzanpirani/pi-jev-skill-picker/blob/5a8b300e1adb9b72f53e7cb5952ec8f7e90c758d/extensions/jev.ts#L165-L231) / 커뮤니티 스킬 선택 | 스킬마다 Score를 묻고 코드에서 기준·정렬·선택을 처리합니다. | 스킬 선택 사례이며 브라우저 요소별 채점 권고가 아닙니다. 질문은 작업 맥락과 대상 설명을 유지합니다. |
| [Foreman](https://github.com/thruwire/foreman/blob/e5d1aa45183382390e388512dcbfebd747ec89ba/src/foreman/foreman/jev.py#L109-L151) / 커뮤니티 감독 구현 | 근거 제공자가 같은 Noul 질문을 묶고 책임 모듈과 코드가 지시를 정합니다. | 근거가 같으면 묶고 다르면 분리합니다. |
| [neo4jev](https://github.com/jexp/neo4jev/blob/d157bbe496eb91813475156942bef1c6badfb342/src/neo4jev/navigator.py#L389-L435) / 커뮤니티 그래프 탐색 | 다음 간선 Choice와 현재 목표 충족 Noul을 함께 묻고 코드가 탐색 예산을 적용합니다. | 행동 후보가 없는 끝 상태에서도 완료 판단은 가능합니다. |

WorkflowEvals의 [정책 조합](https://github.com/typesafe-ai/WorkflowEvals/blob/0ac3b8ad845429f0d8e064ecfb2430a47c5a25cb/evals/invoice_processing/structured/decompose.py#L167-L197),
브라우저 사례의 [실행 전 게이트](https://github.com/jkudish/jev-browser/blob/1f0726cc8bc4483b96439504b594a01596d8e347/src/navigate.ts#L799-L859),
Foreman의 [명시된 검증 한계](https://github.com/thruwire/foreman/blob/e5d1aa45183382390e388512dcbfebd747ec89ba/README.md#L477-L487)도 확인했습니다.
운영 성능이나 정확도를 보증하는 자료로 취급하지 않습니다.

## 핵심 해석

[공식 GitHub 지침](https://github.com/typesafe-ai/skills/blob/65a39f393687675ce170e6094757de20370365b9/skills/typesafe-ai/SKILL.md#L95-L148)은 제한된 행동 선택 자체도 유효한 사용으로
설명하며, 좁은 판단이 문자 그대로의 개별 사실 추출만 뜻하지 않는다고 명시합니다.
따라서 현재 구조가 Jev의 본질을 전혀 사용하지 못한다는 단정은
근거보다 강합니다. 보완할 지점은 **작업 전체의 관련 맥락과 관계를 보존해
판단하는 입력 구조 및 호출 단위**입니다. 개별 요소의 점수만 조합해 작업 의미를
대체하거나, 요소마다 API 요청을 보내는 방식은 제안하지 않습니다.

Choice는 후보 사이 비교, Noul은 참의 확률, Score는 정의한 단계의 위치입니다.
같은 요청의 질문들은 서로의 답을 볼 수 없으므로 선택된 행동에 대한 후속 질문은
새 요청이 필요하거나, 후보별 가정을 명시한 독립 질문으로 미리 물어야 합니다.
모델의 확률·confidence·실제 관찰·실행 권한은 구분해야 합니다.
[공식 개요](https://docs.typesafe.ai/concepts/system-one),
[설계 가이드](https://docs.typesafe.ai/concepts/how-to-build-with-system-one),
[confidence 문서](https://docs.typesafe.ai/confidence)도 이를 설명합니다.
입력은 텍스트/JSON이며 이미지·음성·영상 직접 인식은 현재 지원하지 않습니다.

## 현재 코드와 차이

분석 기준: `himomohi/aside-jev@969d7b5b93971f6e96fc855fc23731d19a38b2a4`.

| 확인한 코드 | 변경 제안 |
| :--- | :--- |
| [`system_one`은 세 타입과 최대 질문 32개를 지원](https://github.com/himomohi/aside-jev/blob/969d7b5b93971f6e96fc855fc23731d19a38b2a4/src/aside_jev/jev.py#L202-L258) | 기존 기반을 재사용합니다. |
| [`choose_live`는 `aside_action` 하나만 생성](https://github.com/himomohi/aside-jev/blob/969d7b5b93971f6e96fc855fc23731d19a38b2a4/src/aside_jev/jev.py#L160-L198) | 관계가 보존된 상태에서 현재 작업 전환을 평가하고 필요한 출력만 한 요청에 묶습니다. |
| [브라우저 루프는 분포를 버리고 행동 confidence 기준을 적용](https://github.com/himomohi/aside-jev/blob/969d7b5b93971f6e96fc855fc23731d19a38b2a4/src/aside_jev/browser_flow.py#L126-L165) | 분포와 근거 누락을 보존하되 기존 게이트를 임의로 낮추지 않습니다. |
| [완료 Noul·위험 Score는 브라우저 완료 후 수행](https://github.com/himomohi/aside-jev/blob/969d7b5b93971f6e96fc855fc23731d19a38b2a4/src/aside_jev/mcp_server.py#L243-L288) | 이미 허용된 작업 전환을 실행 전에 평가하고, 새 사후 근거의 최종 평가는 유지합니다. |
| [완료 Noul과 위험 confidence에 같은 기준 적용](https://github.com/himomohi/aside-jev/blob/969d7b5b93971f6e96fc855fc23731d19a38b2a4/src/aside_jev/mcp_server.py#L281-L284) | 타입과 결과의 영향별 기준을 검증합니다. |
| [관련 줄 압축과 생략 수 기록](https://github.com/himomohi/aside-jev/blob/969d7b5b93971f6e96fc855fc23731d19a38b2a4/src/aside_jev/browser_flow.py#L45-L68) | 관계·범위·근거 누락도 표시합니다. |

다른 프로젝트의 임계값, 자동 재시도, 낮은 confidence 무시, 대체 행동 실행,
텍스트 생성 모델, 넓은 DOM 행동 공간은 그대로 가져오지 않습니다. 기존
정확한 대상·오래된 화면·ON/OFF·권한·시간 예산·수동 재개 검증을 유지합니다.
이 조사만으로 실제 속도나 정확도 향상을 주장하지 않습니다.
