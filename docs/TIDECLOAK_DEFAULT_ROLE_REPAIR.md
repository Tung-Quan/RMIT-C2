# FairEnrol: phương án sửa role mặc định

Trạng thái ngày 22/10/2026: người dùng đã cho phép ngoại lệ sửa một dòng local; **đã áp dụng riêng cho tài khoản quản trị và xác nhận đăng nhập Tide/API thật thành công**. CR quản trị vẫn PENDING; 24 tài khoản khác chưa được sửa offline.

## Lỗi đã xác định

Lượt đăng nhập mới ngày 22/10/2026 trả `TIDE-ORK-ATTESTATION-INVALID` tại PreSign:

```text
token claim 'aud' does not match attested value
token=["fairenrol-client","realm-management"]
attested=["account","fairenrol-client","realm-management"]
```

Script import seed chỉ gán role ứng dụng, bỏ sót `default-roles-fairenrol`. Keycloak vì vậy không thêm audience `account`; ORK tính role mặc định là quyền thừa kế toàn realm từ dữ liệu đã chứng thực. Role này có các quyền account tự phục vụ và capability mặc định, không chứa registrar, approver hay quyền quản trị realm.

`scripts/tide-setup.mjs` đã được sửa để import cả role mặc định, kiểm tra các mapping trước khi hoàn tất bootstrap, và từ chối tự sửa một realm đã chuyển sang MultiAdmin.

## Kết quả thử trên bản sao

- 25 tài khoản seed thiếu dòng mapping mặc định.
- Bổ sung mapping trên bản sao H2 trong `.local/diagnostics/repair-preview/`.
- Chạy cùng image TideCloak, xuất token preview qua endpoint chẩn đoán chuẩn: FairEnrol có `aud=["fairenrol-client","realm-management","account"]`.
- Kiểm tra lại chữ ký: FairEnrol **97/97**, console **92/92** hợp lệ.
- Container bản sao đã được dừng và gỡ. Kết quả bản sao chỉ là kiểm tra trước sửa; bằng chứng đăng nhập thật được ghi riêng bên dưới.

## Vì sao cần quyết định cho realm thật

Trước ngoại lệ, yêu cầu gán role qua API chuẩn đã tạo CR `1623e3b2-14c0-4d0b-9aec-29a0f425d1e7`, action `GRANT_ROLES`, trạng thái PENDING; mapping lúc đó chưa được áp dụng. Không tự ký hay commit CR này bằng backend.

Theo Tide MCP, canon `iga-change-requests-api.md`, mục “The automation cliff”:

> multiAdmin change requests must be approved via the approval enclave

Realm đã ở MultiAdmin, nhưng tài khoản phê duyệt hiện không lấy được token vì chính lỗi mapping đó. Vì vậy sửa qua luồng phê duyệt thông thường đang mắc vòng phụ thuộc. Sửa trực tiếp dữ liệu local là một ngoại lệ đối với luồng quản trị, cần người dùng cho phép rõ ràng.

## Phạm vi ngoại lệ được đề xuất

**Chỉ bổ sung một dòng mapping role mặc định cho tài khoản quản trị đã liên kết.** Không sửa 24 tài khoản còn lại bằng phương án offline. Sau khi quản trị đăng nhập được, xử lý CR đang chờ và các tài khoản khác qua luồng Tide chuẩn.

Dạng câu lệnh trên bản sao offline, với tham số lấy từ realm/tài khoản đã kiểm tra:

```sql
INSERT INTO USER_ROLE_MAPPING (ROLE_ID, USER_ID, ATTESTATION)
VALUES (:existing_realm_default_role_id, :linked_registrar_user_id, NULL);
```

Dòng role mặc định này bị loại khỏi attestation per-user theo thiết kế của Tide; quyền mặc định đã được chứng thực ở cấp realm. Không tạo chữ ký giả hoặc thay đổi quyền quản trị. Việc sửa làm cho dữ liệu local khớp với quyền mặc định mà ORK đã tính; chỉ thực hiện sau câu trả lời rõ ràng của người dùng: “Cho phép sửa một dòng local”.

Quy trình đã chuẩn bị trong `.local/diagnostics/repair-owner-default.ps1`:

1. Dừng TideCloak và sao lưu H2 mới nhất.
2. Sửa đúng mapping của một tài khoản trên bản staging; kiểm tra composite chỉ chứa 8 role mặc định đã xác định là benign.
3. Xác minh lại toàn bộ 189 chữ ký trước khi đưa bản staging trở lại container.
4. Khởi động, kiểm tra readiness; phục hồi backup nếu triển khai/health thất bại.
5. Giữ CR đang chờ, kiểm tra đăng nhập thật, hoàn tất việc phê duyệt qua Tide và tháo bộ ghi lỗi tạm.

Không xoá/tạo lại realm, không tắt IGA/DPoP và không thay signer. Licence, người dùng đã liên kết và dữ liệu FairEnrol được giữ nguyên.

## Kết quả áp dụng

- Snapshot trước sửa: `.local/diagnostics/owner-repair-stage/20261022-050827/backup/keycloakdb.mv.db`.
- Staging phát hiện và bổ sung đúng **1** mapping; kiểm tra **189/189** chữ ký vẫn hợp lệ trước khi thay file database.
- TideCloak đã khởi động và qua readiness. API read xác nhận owner có role mặc định; IGA vẫn `true`/`tide`.
- Token preview của realm thật có `aud=["fairenrol-client","realm-management","account"]`.
- CR trên vẫn PENDING, chưa ghi approval giả. 24 tài khoản seed khác chưa được sửa offline.
- `npm run verify` đã qua sau khi khởi động lại web/API.
- Đăng nhập thật đã thành công: dashboard **Taylor Reed / Registrar** tải được dữ liệu khóa học qua API bảo vệ bằng JWT Tide và DPoP. Observer ghi nhận 14 phản hồi Sign HTTP 200 trong lượt thành công (một PreSign timeout riêng lẻ không làm mất quorum).
- Đã gỡ container observer, proxy và trust bundle chẩn đoán khỏi TideCloak đang chạy. Reload app sau khi khởi động lại container bình thường vẫn trả dashboard và dữ liệu thật.
- Đã thử console SPA, console Keycloak và panel SDK tạm trên origin FairEnrol. Panel dùng `secureFetch` bằng token của người quản trị, `/approve` hai pha và `approveTideRequests`; API trả `needs-approval` nhưng cửa sổ enclave không xuất hiện trong browser panel. Chưa có chữ ký phê duyệt; không kết luận đây là lỗi API hay do relay khi chưa đủ bằng chứng.
- Kiểm tra cuối: owner có mapping, IGA vẫn bật, CR trên còn **PENDING, 0/1** và **24** tài khoản khác còn thiếu mapping. Không mở thêm CR hàng loạt khi ceremony chưa hoạt động.
- Build và 15 bài kiểm tra API qua; Tide Doctor: 15 PASS, 1 WARN về CR pending, 0 FAIL.

![Dashboard sau sửa và khôi phục transport bình thường](images/fairenrol-tide-login-success.png)
