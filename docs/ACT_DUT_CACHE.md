# Stable ACT DUT manifest for Linux replay

`build_act4_dut.py`가 동일 소스에서도 smoke 실행 시간과 로그 해시를
다시 기록해 `model.json`의 SHA가 바뀌었다. Linux 모델은 이 파일의 SHA를
base model 근거로 사용하므로 불필요한 재호출이 기존 부팅 근거를 무효화했다.

현재는 RTL/TB/include와 filelist 순서, 파라미터, executable, smoke ELF,
boot ROM, builder 및 smoke 로그의 해시가 일치하면 검증된 manifest 바이트를
유지한다. Smoke 입력이나 로그가 달라지면 재검사한다. 검사를 시작하기 전에
passed=false를 저장하고, 성공한 뒤 atomic replacement로 결과를 기록한다.

`check_act4_dut_cache.py`에서 다음을 확인했다.

- 변경 없는 재호출은 cached 결과를 사용하고 manifest SHA를 유지한다.
- Smoke 로그를 손상시킨 경우 같은 compiled executable로 smoke를 다시 실행한다.
- 재실행 후 변경 없는 호출도 manifest SHA를 유지한다.

소스가 현재인 full H/V ACT DUT와 scalar smoke를 사용했다. 이 결과는
**전체 ACT 테스트 실행이 아니다**. [검사 해시 근거](evidence/act_dut_cache.json).

```powershell
python scripts/build_act4_dut.py
python scripts/check_act4_dut_cache.py
```

캐시 검사는 로그 손상 대조군을 포함하므로 Linux 부팅을 시작하기 전에 실행한다.
최신 RTL의 Linux 6.14 Supm/vector 재실행은 별도 variant
`vector_bare_supm`에서 진행 중이다. 기존 32MiB 데모의 동일 firmware/image를
사용하며 production SRAM 1MiB 설정을 바꾸지 않는다.
