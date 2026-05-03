# MÔ TẢ HỆ THỐNG PHARMA MONITOR PRO (NEXT.JS & SUPABASE VERSION)

## a. Giao diện giám sát hiện đại trên nền tảng Next.js
Hệ thống **Pharma Monitor Pro** sử dụng framework **Next.js** làm nền tảng hiển thị chính. Đây không chỉ là một thư viện UI thông thường mà là một framework React mạnh mẽ, mang lại trải nghiệm HMI (Human-Machine Interface) ở đẳng cấp công nghiệp:

*   **Tối ưu hóa tuyệt đối cho hệ sinh thái Vercel:** Nhóm nghiên cứu quyết định lựa chọn Next.js vì dự án được triển khai trực tiếp trên nền tảng Cloud của **Vercel**. Do Vercel chính là đơn vị phát triển Next.js, việc kết hợp này đảm bảo tính tương thích hoàn hảo, giúp tận dụng tối đa các tính năng cao cấp như *Edge Functions*, *Image Optimization* và cơ chế *Caching* thông minh. Điều này giúp Dashboard đạt tốc độ phản hồi cực nhanh, đảm bảo tính liên tục trong việc giám sát dây chuyền sản xuất.
*   **Trải nghiệm người dùng đa nền tảng (Responsive Design):** Giao diện được xây dựng với tư duy hiện đại, đảm bảo hoạt động mượt mà từ các màn hình máy tính công nghiệp tại nhà máy đến các thiết bị di động cá nhân. Chế độ Dark Mode cùng bố cục khoa học giúp kỹ thuật viên quan sát luồng video AI và các thông số vận hành trong thời gian dài mà không gây mỏi mắt.
*   **Quản lý trạng thái và Dữ liệu thời gian thực:** Dashboard tận dụng sức mạnh của React Components để hiển thị thời gian thực các chỉ số sản lượng (OK/NG), trạng thái sản phẩm và tốc độ băng tải thông qua các biểu đồ động và đồng hồ đo trực quan. Mọi biến động trên dây chuyền đều được phản ánh lên giao diện ngay lập tức nhờ cơ chế đồng bộ hóa dữ liệu hiện đại.
*   **Hệ thống phân quyền người dùng (RBAC):** Tích hợp khả năng quản lý quyền truy cập nghiêm ngặt. Hệ thống tự động nhận diện và phân cấp người dùng dựa trên danh tính:
    *   **Administrator:** Có toàn quyền giám sát và thực hiện các lệnh điều khiển hệ thống như chuyển đổi công thức sản xuất (Recipe Switching) và thay đổi cấu hình vận hành.
    *   **Operator:** Chỉ được cấp quyền giám sát dữ liệu thực tế mà không thể can thiệp vào các thông số cốt lõi, giúp đảm bảo an toàn vận hành tuyệt đối.

## b. Backend Cloud và Quản lý dữ liệu tập trung (Supabase)
Hệ thống tích hợp **Supabase** làm nền tảng Backend-as-a-Service (BaaS), đóng vai trò là "bộ não" lưu trữ dữ liệu của toàn bộ quy trình:

*   **Cơ sở dữ liệu Real-time:** Sử dụng PostgreSQL với tính năng Real-time để đồng bộ hóa dữ liệu sản xuất từ Edge Server lên Cloud ngay lập tức. Điều này đảm bảo Dashboard luôn hiển thị thông tin mới nhất mà không có độ trễ.
*   **Quản lý bảo mật và Xác thực:** Sử dụng Supabase Auth để quản lý danh tính người dùng. Hệ thống phân quyền dựa trên Metadata của tài khoản, giúp bảo vệ dữ liệu sản xuất nhạy cảm và kiểm soát chặt chẽ quyền hạn của từng cấp bậc nhân sự.
*   **Lưu trữ lịch sử và Phân tích:** Supabase lưu trữ toàn bộ lịch sử sản xuất, cho phép người dùng truy xuất dữ liệu quá khứ, xuất báo cáo năng suất và theo dõi xu hướng hoạt động của dây chuyền theo thời gian.

## c. Triển khai Cloud và Tự động hóa (Vercel & GitHub CI/CD)
Hệ thống được tối ưu hóa quy trình vận hành nhờ sự kết hợp chặt chẽ với các công nghệ Cloud tiên tiến:

*   **Deployment trên Vercel:** Toàn bộ ứng dụng Next.js được triển khai trên nền tảng **Vercel**, cho phép truy cập Dashboard từ xa qua internet một cách ổn định và bảo mật cao mà không cần thiết lập server vật lý phức tạp.
*   **Quy trình CI/CD tự động qua GitHub:** Hệ thống được đồng bộ hóa hoàn toàn với **GitHub**. Mỗi khi có sự thay đổi về mã nguồn, kỹ thuật viên chỉ cần thực hiện thao tác `push` code. Ngay lập tức, **Vercel sẽ tự động kích hoạt quy trình Build và Deploy lại web**, giúp các cập nhật về giao diện và tính năng được áp dụng ngay tức thì.
*   **Giám sát di động an toàn:** Nhờ sức mạnh của Cloud và hệ thống phân quyền, việc theo dõi năng suất từ điện thoại trở nên dễ dàng và an toàn. Người dùng vẫn phải tuân thủ đúng quyền hạn đã được cấp phát, đảm bảo an toàn tuyệt đối cho hệ thống máy móc ngay cả khi quản lý từ xa.

---
*Ghi chú: Sự kết hợp giữa Next.js, Supabase và Vercel tạo nên một hệ sinh thái giám sát sản xuất hiện đại, bảo mật và có khả năng mở rộng cực cao.*
