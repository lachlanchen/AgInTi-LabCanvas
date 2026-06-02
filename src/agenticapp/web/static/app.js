const TRANSLATIONS = {
  en: {
    "app.title": "Paper Figure Studio",
    "button.reset": "Reset",
    "button.openscad": "OpenSCAD",
    "button.figureGrid": "Figure Grid",
    "button.render": "Render",
    "button.dark": "Dark",
    "button.light": "Light",
    "button.send": "Send",
    "button.dispatchTarget": "Dispatch Target",
    "button.saveSettings": "Save Settings",
    "button.openBioRender": "Open BioRender",
    "button.applyJson": "Apply JSON",
    "button.dryRun": "Dry Run",
    "section.chat": "Chat",
    "section.canvas": "Canvas",
    "section.scene": "Scene",
    "section.backends": "Backends",
    "status.ready": "Ready",
    "status.thinking": "Thinking",
    "status.idle": "Idle",
    "status.rendering": "Rendering",
    "status.rendered": "Rendered",
    "status.error": "Error",
    "status.planOk": "Plan OK",
    "status.planError": "Plan error",
    "status.generatingGrid": "Generating grid",
    "status.gridReady": "Grid ready",
    "status.gridError": "Grid error",
    "status.exportingCad": "Exporting CAD",
    "status.cadReady": "CAD ready",
    "status.cadError": "CAD error",
    "status.dispatching": "Dispatching",
    "status.dispatchReady": "Dispatch ready",
    "status.dispatchError": "Dispatch error",
    "status.loading": "Loading",
    "chip.figure2x3": "Figure 2x3",
    "chip.vivid": "Vivid",
    "chip.addLens": "Add lens",
    "chip.addFilter": "Add filter",
    "placeholder.message": "Ask for a paper setup, optical bench, device concept, labels, colors, or generated figure panels.",
    "placeholder.targetInstruction": "Dry-run an instruction for any configured target.",
    "label.prompt": "Prompt",
    "label.rows": "Rows",
    "label.cols": "Cols",
    "label.title": "Title",
    "label.slug": "Slug",
    "label.agintiCommand": "AgInTi command",
    "label.agintiWorkspace": "AgInTi workspace",
    "label.provider": "Provider",
    "label.model": "Model",
    "label.biorenderUrl": "BioRender MCP URL",
    "label.biorenderEnv": "BioRender auth env",
    "label.agintiDryRun": "AgInTi dry run",
    "label.blenderRender": "Blender render",
    "label.openscadExport": "OpenSCAD export",
    "label.agintiImage": "AgInTi image",
    "label.biorenderMcp": "BioRender MCP",
    "label.targetRegistry": "Target registry",
    "label.registryTarget": "Registry target",
    "label.targetInstruction": "Target instruction",
    "label.dryRun": "Dry run",
    "artifact.noneSelected": "Nothing selected",
    "artifact.metaEmpty": "Generated artifacts appear here.",
    "artifact.previewAlt": "Selected artifact preview",
    "artifact.noneYet": "No artifact yet",
    "artifact.emptyHint": "Render, export, or generate a figure grid.",
    "artifact.noArtifacts": "No artifacts yet.",
    "artifact.path": "Artifact path",
    "link.image": "Image",
    "link.blend": "Blend",
    "link.spec": "Spec",
    "message.sceneLoaded": "Scene loaded. Ask for components, paper figure grids, OpenSCAD exports, or BioRender setup.",
    "message.sceneJsonApplied": "Scene JSON applied.",
    "message.backendSettingsSaved": "Backend settings saved.",
    "message.chooseTargetFirst": "Choose a target and enter an instruction first.",
    "message.rendered": "Rendered {title}.",
    "message.planOk": "Plan OK: {path}",
    "message.gridGenerated": "Generated a {rows}x{cols} paper figure grid.",
    "message.exportedOpenScad": "Exported OpenSCAD: {path}",
    "message.targetDispatch": "Target dispatch {status}: {target}.",
    "backend.agintiReady": "AgInTi ready",
    "backend.agintiMissing": "AgInTi missing",
    "backend.bioPresent": "BioRender key present",
    "backend.bioEnv": "BioRender key via env",
    "aria.switchLight": "Switch to bright theme",
    "aria.switchDark": "Switch to dark theme",
    "count.elements": "{count} elements",
  },
  ar: {
    "app.title": "استوديو أشكال الأوراق",
    "button.reset": "إعادة ضبط",
    "button.figureGrid": "شبكة الأشكال",
    "button.render": "رندر",
    "button.dark": "داكن",
    "button.light": "فاتح",
    "button.send": "إرسال",
    "button.dispatchTarget": "إرسال للهدف",
    "button.saveSettings": "حفظ الإعدادات",
    "button.openBioRender": "فتح BioRender",
    "button.applyJson": "تطبيق JSON",
    "button.dryRun": "تشغيل تجريبي",
    "section.chat": "الدردشة",
    "section.canvas": "اللوحة",
    "section.scene": "المشهد",
    "section.backends": "الخلفيات",
    "status.ready": "جاهز",
    "status.thinking": "يفكر",
    "status.idle": "خامل",
    "status.rendering": "يتم الرندر",
    "status.rendered": "تم الرندر",
    "status.error": "خطأ",
    "status.loading": "تحميل",
    "chip.figure2x3": "شكل 2x3",
    "chip.vivid": "حيوي",
    "chip.addLens": "إضافة عدسة",
    "chip.addFilter": "إضافة مرشح",
    "placeholder.message": "اطلب إعداد ورقة أو منصة بصرية أو مفهوم جهاز أو تسميات أو ألوان أو لوحات شكل.",
    "placeholder.targetInstruction": "نفذ تعليمات تجريبية لأي هدف مضبوط.",
    "label.prompt": "الموجه",
    "label.rows": "الصفوف",
    "label.cols": "الأعمدة",
    "label.title": "العنوان",
    "label.slug": "المعرف",
    "label.provider": "المزود",
    "label.model": "النموذج",
    "label.agintiCommand": "أمر AgInTi",
    "label.agintiWorkspace": "مساحة AgInTi",
    "label.biorenderUrl": "رابط BioRender MCP",
    "label.biorenderEnv": "متغير BioRender",
    "label.agintiDryRun": "تشغيل AgInTi تجريبي",
    "label.blenderRender": "رندر Blender",
    "label.openscadExport": "تصدير OpenSCAD",
    "label.agintiImage": "صورة AgInTi",
    "label.biorenderMcp": "BioRender MCP",
    "label.targetRegistry": "سجل الأهداف",
    "label.registryTarget": "هدف السجل",
    "label.targetInstruction": "تعليمات الهدف",
    "label.dryRun": "تشغيل تجريبي",
    "artifact.noneSelected": "لا يوجد تحديد",
    "artifact.metaEmpty": "تظهر النتائج المولدة هنا.",
    "artifact.previewAlt": "معاينة النتيجة المحددة",
    "artifact.noneYet": "لا توجد نتيجة بعد",
    "artifact.emptyHint": "قم بالرندر أو التصدير أو إنشاء شبكة أشكال.",
    "artifact.noArtifacts": "لا توجد نتائج بعد.",
    "link.image": "صورة",
    "link.blend": "Blend",
    "link.spec": "المواصفة",
    "message.sceneLoaded": "تم تحميل المشهد. اطلب مكونات أو شبكات أشكال أو تصدير OpenSCAD أو إعداد BioRender.",
    "message.sceneJsonApplied": "تم تطبيق JSON للمشهد.",
    "message.backendSettingsSaved": "تم حفظ إعدادات الخلفية.",
    "message.chooseTargetFirst": "اختر هدفا وأدخل التعليمات أولا.",
    "backend.agintiReady": "AgInTi جاهز",
    "backend.agintiMissing": "AgInTi غير موجود",
    "backend.bioPresent": "مفتاح BioRender موجود",
    "backend.bioEnv": "مفتاح BioRender عبر البيئة",
    "count.elements": "{count} عناصر",
  },
  es: {
    "app.title": "Estudio de Figuras",
    "button.reset": "Restablecer",
    "button.figureGrid": "Cuadrícula",
    "button.render": "Renderizar",
    "button.dark": "Oscuro",
    "button.light": "Claro",
    "button.send": "Enviar",
    "button.dispatchTarget": "Enviar objetivo",
    "button.saveSettings": "Guardar ajustes",
    "button.openBioRender": "Abrir BioRender",
    "button.applyJson": "Aplicar JSON",
    "button.dryRun": "Prueba seca",
    "section.chat": "Chat",
    "section.canvas": "Lienzo",
    "section.scene": "Escena",
    "section.backends": "Backends",
    "status.ready": "Listo",
    "status.thinking": "Pensando",
    "status.idle": "Inactivo",
    "status.rendering": "Renderizando",
    "status.rendered": "Renderizado",
    "status.error": "Error",
    "status.loading": "Cargando",
    "chip.figure2x3": "Figura 2x3",
    "chip.vivid": "Vívido",
    "chip.addLens": "Añadir lente",
    "chip.addFilter": "Añadir filtro",
    "placeholder.message": "Pide una figura, banco óptico, concepto de dispositivo, etiquetas, colores o paneles generados.",
    "placeholder.targetInstruction": "Prueba una instrucción para cualquier objetivo configurado.",
    "label.prompt": "Prompt",
    "label.rows": "Filas",
    "label.cols": "Columnas",
    "label.title": "Título",
    "label.slug": "Slug",
    "label.provider": "Proveedor",
    "label.model": "Modelo",
    "label.agintiCommand": "Comando AgInTi",
    "label.agintiWorkspace": "Espacio AgInTi",
    "label.biorenderUrl": "URL MCP de BioRender",
    "label.biorenderEnv": "Env auth de BioRender",
    "label.agintiDryRun": "Prueba seca AgInTi",
    "label.blenderRender": "Render Blender",
    "label.openscadExport": "Exportar OpenSCAD",
    "label.agintiImage": "Imagen AgInTi",
    "label.biorenderMcp": "BioRender MCP",
    "label.targetRegistry": "Registro de objetivos",
    "label.registryTarget": "Objetivo",
    "label.targetInstruction": "Instrucción",
    "label.dryRun": "Prueba seca",
    "artifact.noneSelected": "Nada seleccionado",
    "artifact.metaEmpty": "Los artefactos generados aparecen aquí.",
    "artifact.previewAlt": "Vista previa del artefacto seleccionado",
    "artifact.noneYet": "Sin artefactos",
    "artifact.emptyHint": "Renderiza, exporta o genera una cuadrícula.",
    "artifact.noArtifacts": "Sin artefactos todavía.",
    "link.image": "Imagen",
    "link.blend": "Blend",
    "link.spec": "Spec",
    "message.sceneLoaded": "Escena cargada. Pide componentes, cuadrículas, exportes OpenSCAD o ajustes BioRender.",
    "message.sceneJsonApplied": "JSON de escena aplicado.",
    "message.backendSettingsSaved": "Ajustes guardados.",
    "message.chooseTargetFirst": "Elige un objetivo e introduce una instrucción.",
    "backend.agintiReady": "AgInTi listo",
    "backend.agintiMissing": "Falta AgInTi",
    "backend.bioPresent": "Clave BioRender presente",
    "backend.bioEnv": "Clave BioRender por env",
    "count.elements": "{count} elementos",
  },
  fr: {
    "app.title": "Studio de Figures",
    "button.reset": "Réinitialiser",
    "button.figureGrid": "Grille",
    "button.render": "Rendre",
    "button.dark": "Sombre",
    "button.light": "Clair",
    "button.send": "Envoyer",
    "button.dispatchTarget": "Envoyer cible",
    "button.saveSettings": "Enregistrer",
    "button.openBioRender": "Ouvrir BioRender",
    "button.applyJson": "Appliquer JSON",
    "button.dryRun": "Essai à blanc",
    "section.chat": "Chat",
    "section.canvas": "Canevas",
    "section.scene": "Scène",
    "section.backends": "Backends",
    "status.ready": "Prêt",
    "status.thinking": "Réflexion",
    "status.idle": "Inactif",
    "status.rendering": "Rendu",
    "status.rendered": "Rendu terminé",
    "status.error": "Erreur",
    "status.loading": "Chargement",
    "chip.figure2x3": "Figure 2x3",
    "chip.vivid": "Vif",
    "chip.addLens": "Ajouter lentille",
    "chip.addFilter": "Ajouter filtre",
    "placeholder.message": "Demandez une figure, un banc optique, un concept, des libellés, couleurs ou panneaux.",
    "placeholder.targetInstruction": "Tester une instruction pour une cible configurée.",
    "label.prompt": "Prompt",
    "label.rows": "Lignes",
    "label.cols": "Colonnes",
    "label.title": "Titre",
    "label.slug": "Slug",
    "label.provider": "Fournisseur",
    "label.model": "Modèle",
    "label.agintiCommand": "Commande AgInTi",
    "label.agintiWorkspace": "Espace AgInTi",
    "label.biorenderUrl": "URL MCP BioRender",
    "label.biorenderEnv": "Env auth BioRender",
    "label.agintiDryRun": "Essai AgInTi",
    "label.blenderRender": "Rendu Blender",
    "label.openscadExport": "Export OpenSCAD",
    "label.agintiImage": "Image AgInTi",
    "label.biorenderMcp": "BioRender MCP",
    "label.targetRegistry": "Registre cibles",
    "label.registryTarget": "Cible",
    "label.targetInstruction": "Instruction",
    "label.dryRun": "Essai à blanc",
    "artifact.noneSelected": "Rien sélectionné",
    "artifact.metaEmpty": "Les artefacts générés apparaissent ici.",
    "artifact.previewAlt": "Aperçu de l'artefact sélectionné",
    "artifact.noneYet": "Aucun artefact",
    "artifact.emptyHint": "Rendez, exportez ou générez une grille.",
    "artifact.noArtifacts": "Aucun artefact pour l'instant.",
    "link.image": "Image",
    "message.sceneLoaded": "Scène chargée. Demandez composants, grilles, exports OpenSCAD ou réglages BioRender.",
    "message.sceneJsonApplied": "JSON de scène appliqué.",
    "message.backendSettingsSaved": "Réglages enregistrés.",
    "message.chooseTargetFirst": "Choisissez une cible et saisissez une instruction.",
    "backend.agintiReady": "AgInTi prêt",
    "backend.agintiMissing": "AgInTi absent",
    "backend.bioPresent": "Clé BioRender présente",
    "backend.bioEnv": "Clé BioRender via env",
    "count.elements": "{count} éléments",
  },
  ja: {
    "app.title": "論文図版スタジオ",
    "button.reset": "リセット",
    "button.figureGrid": "図版グリッド",
    "button.render": "レンダー",
    "button.dark": "ダーク",
    "button.light": "ライト",
    "button.send": "送信",
    "button.dispatchTarget": "ターゲット送信",
    "button.saveSettings": "設定保存",
    "button.openBioRender": "BioRenderを開く",
    "button.applyJson": "JSON適用",
    "button.dryRun": "ドライラン",
    "section.chat": "チャット",
    "section.canvas": "キャンバス",
    "section.scene": "シーン",
    "section.backends": "バックエンド",
    "status.ready": "準備完了",
    "status.thinking": "処理中",
    "status.idle": "待機中",
    "status.rendering": "レンダー中",
    "status.rendered": "レンダー完了",
    "status.error": "エラー",
    "status.loading": "読み込み中",
    "chip.figure2x3": "図 2x3",
    "chip.vivid": "鮮やか",
    "chip.addLens": "レンズ追加",
    "chip.addFilter": "フィルター追加",
    "placeholder.message": "論文図、光学ベンチ、デバイス概念、ラベル、色、生成パネルを依頼します。",
    "placeholder.targetInstruction": "設定済みターゲットへの命令をドライランします。",
    "label.prompt": "プロンプト",
    "label.rows": "行",
    "label.cols": "列",
    "label.title": "タイトル",
    "label.slug": "スラッグ",
    "label.provider": "プロバイダ",
    "label.model": "モデル",
    "label.agintiCommand": "AgInTiコマンド",
    "label.agintiWorkspace": "AgInTiワークスペース",
    "label.biorenderUrl": "BioRender MCP URL",
    "label.biorenderEnv": "BioRender認証env",
    "label.agintiDryRun": "AgInTiドライラン",
    "label.blenderRender": "Blenderレンダー",
    "label.openscadExport": "OpenSCAD出力",
    "label.agintiImage": "AgInTi画像",
    "label.biorenderMcp": "BioRender MCP",
    "label.targetRegistry": "ターゲット登録",
    "label.registryTarget": "登録ターゲット",
    "label.targetInstruction": "ターゲット命令",
    "label.dryRun": "ドライラン",
    "artifact.noneSelected": "未選択",
    "artifact.metaEmpty": "生成アーティファクトがここに表示されます。",
    "artifact.previewAlt": "選択アーティファクトのプレビュー",
    "artifact.noneYet": "まだありません",
    "artifact.emptyHint": "レンダー、出力、またはグリッド生成を行います。",
    "artifact.noArtifacts": "アーティファクトはまだありません。",
    "link.image": "画像",
    "message.sceneLoaded": "シーンを読み込みました。部品、図版グリッド、OpenSCAD出力、BioRender設定を依頼できます。",
    "message.sceneJsonApplied": "シーンJSONを適用しました。",
    "message.backendSettingsSaved": "バックエンド設定を保存しました。",
    "message.chooseTargetFirst": "ターゲットを選び、命令を入力してください。",
    "backend.agintiReady": "AgInTi準備完了",
    "backend.agintiMissing": "AgInTiなし",
    "backend.bioPresent": "BioRenderキーあり",
    "backend.bioEnv": "BioRenderキーはenv経由",
    "count.elements": "{count}要素",
  },
  ko: {
    "app.title": "논문 그림 스튜디오",
    "button.reset": "초기화",
    "button.figureGrid": "그림 그리드",
    "button.render": "렌더",
    "button.dark": "다크",
    "button.light": "라이트",
    "button.send": "보내기",
    "button.dispatchTarget": "대상 전송",
    "button.saveSettings": "설정 저장",
    "button.openBioRender": "BioRender 열기",
    "button.applyJson": "JSON 적용",
    "button.dryRun": "드라이런",
    "section.chat": "채팅",
    "section.canvas": "캔버스",
    "section.scene": "장면",
    "section.backends": "백엔드",
    "status.ready": "준비",
    "status.thinking": "생각 중",
    "status.idle": "대기",
    "status.rendering": "렌더링",
    "status.rendered": "렌더됨",
    "status.error": "오류",
    "status.loading": "불러오는 중",
    "chip.figure2x3": "그림 2x3",
    "chip.vivid": "선명하게",
    "chip.addLens": "렌즈 추가",
    "chip.addFilter": "필터 추가",
    "placeholder.message": "논문 설정, 광학 벤치, 장치 개념, 라벨, 색상 또는 그림 패널을 요청하세요.",
    "placeholder.targetInstruction": "설정된 대상에 대한 명령을 드라이런합니다.",
    "label.prompt": "프롬프트",
    "label.rows": "행",
    "label.cols": "열",
    "label.title": "제목",
    "label.slug": "슬러그",
    "label.provider": "제공자",
    "label.model": "모델",
    "label.agintiCommand": "AgInTi 명령",
    "label.agintiWorkspace": "AgInTi 작업공간",
    "label.biorenderUrl": "BioRender MCP URL",
    "label.biorenderEnv": "BioRender 인증 env",
    "label.agintiDryRun": "AgInTi 드라이런",
    "label.blenderRender": "Blender 렌더",
    "label.openscadExport": "OpenSCAD 내보내기",
    "label.agintiImage": "AgInTi 이미지",
    "label.biorenderMcp": "BioRender MCP",
    "label.targetRegistry": "대상 레지스트리",
    "label.registryTarget": "레지스트리 대상",
    "label.targetInstruction": "대상 명령",
    "label.dryRun": "드라이런",
    "artifact.noneSelected": "선택 없음",
    "artifact.metaEmpty": "생성된 아티팩트가 여기에 표시됩니다.",
    "artifact.previewAlt": "선택한 아티팩트 미리보기",
    "artifact.noneYet": "아직 없음",
    "artifact.emptyHint": "렌더, 내보내기 또는 그리드 생성을 실행하세요.",
    "artifact.noArtifacts": "아직 아티팩트가 없습니다.",
    "link.image": "이미지",
    "message.sceneLoaded": "장면을 불러왔습니다. 구성요소, 그림 그리드, OpenSCAD 내보내기 또는 BioRender 설정을 요청하세요.",
    "message.sceneJsonApplied": "장면 JSON을 적용했습니다.",
    "message.backendSettingsSaved": "백엔드 설정을 저장했습니다.",
    "message.chooseTargetFirst": "대상을 선택하고 명령을 입력하세요.",
    "backend.agintiReady": "AgInTi 준비됨",
    "backend.agintiMissing": "AgInTi 없음",
    "backend.bioPresent": "BioRender 키 있음",
    "backend.bioEnv": "BioRender 키 env",
    "count.elements": "{count}개 요소",
  },
  vi: {
    "app.title": "Studio Hình Bài Báo",
    "button.reset": "Đặt lại",
    "button.figureGrid": "Lưới hình",
    "button.render": "Render",
    "button.dark": "Tối",
    "button.light": "Sáng",
    "button.send": "Gửi",
    "button.dispatchTarget": "Gửi target",
    "button.saveSettings": "Lưu thiết lập",
    "button.openBioRender": "Mở BioRender",
    "button.applyJson": "Áp dụng JSON",
    "button.dryRun": "Dry run",
    "section.chat": "Chat",
    "section.canvas": "Canvas",
    "section.scene": "Scene",
    "section.backends": "Backend",
    "status.ready": "Sẵn sàng",
    "status.thinking": "Đang nghĩ",
    "status.idle": "Rảnh",
    "status.rendering": "Đang render",
    "status.rendered": "Đã render",
    "status.error": "Lỗi",
    "status.loading": "Đang tải",
    "chip.figure2x3": "Hình 2x3",
    "chip.vivid": "Rực rỡ",
    "chip.addLens": "Thêm lens",
    "chip.addFilter": "Thêm filter",
    "placeholder.message": "Yêu cầu setup bài báo, bench quang học, ý tưởng thiết bị, nhãn, màu hoặc panel hình.",
    "placeholder.targetInstruction": "Dry-run một chỉ dẫn cho target đã cấu hình.",
    "label.prompt": "Prompt",
    "label.rows": "Hàng",
    "label.cols": "Cột",
    "label.title": "Tiêu đề",
    "label.slug": "Slug",
    "label.provider": "Nhà cung cấp",
    "label.model": "Model",
    "label.agintiCommand": "Lệnh AgInTi",
    "label.agintiWorkspace": "Workspace AgInTi",
    "label.biorenderUrl": "BioRender MCP URL",
    "label.biorenderEnv": "BioRender auth env",
    "label.agintiDryRun": "AgInTi dry run",
    "label.blenderRender": "Blender render",
    "label.openscadExport": "OpenSCAD export",
    "label.agintiImage": "Ảnh AgInTi",
    "label.biorenderMcp": "BioRender MCP",
    "label.targetRegistry": "Target registry",
    "label.registryTarget": "Target",
    "label.targetInstruction": "Chỉ dẫn target",
    "label.dryRun": "Dry run",
    "artifact.noneSelected": "Chưa chọn",
    "artifact.metaEmpty": "Artifact tạo ra sẽ xuất hiện ở đây.",
    "artifact.previewAlt": "Xem trước artifact đã chọn",
    "artifact.noneYet": "Chưa có artifact",
    "artifact.emptyHint": "Render, export hoặc tạo lưới hình.",
    "artifact.noArtifacts": "Chưa có artifact.",
    "link.image": "Ảnh",
    "message.sceneLoaded": "Đã tải scene. Hãy yêu cầu thành phần, lưới hình, export OpenSCAD hoặc thiết lập BioRender.",
    "message.sceneJsonApplied": "Đã áp dụng JSON scene.",
    "message.backendSettingsSaved": "Đã lưu thiết lập backend.",
    "message.chooseTargetFirst": "Chọn target và nhập chỉ dẫn trước.",
    "backend.agintiReady": "AgInTi sẵn sàng",
    "backend.agintiMissing": "Thiếu AgInTi",
    "backend.bioPresent": "Có khóa BioRender",
    "backend.bioEnv": "Khóa BioRender qua env",
    "count.elements": "{count} phần tử",
  },
  "zh-Hans": {
    "app.title": "论文图形工作室",
    "button.reset": "重置",
    "button.figureGrid": "图形网格",
    "button.render": "渲染",
    "button.dark": "深色",
    "button.light": "浅色",
    "button.send": "发送",
    "button.dispatchTarget": "分发目标",
    "button.saveSettings": "保存设置",
    "button.openBioRender": "打开 BioRender",
    "button.applyJson": "应用 JSON",
    "button.dryRun": "试运行",
    "section.chat": "聊天",
    "section.canvas": "画布",
    "section.scene": "场景",
    "section.backends": "后端",
    "status.ready": "就绪",
    "status.thinking": "思考中",
    "status.idle": "空闲",
    "status.rendering": "渲染中",
    "status.rendered": "已渲染",
    "status.error": "错误",
    "status.loading": "加载中",
    "chip.figure2x3": "图 2x3",
    "chip.vivid": "鲜明",
    "chip.addLens": "添加透镜",
    "chip.addFilter": "添加滤光片",
    "placeholder.message": "请求论文装置、光学平台、设备概念、标签、颜色或生成图形面板。",
    "placeholder.targetInstruction": "对任意已配置目标进行试运行指令。",
    "label.prompt": "提示词",
    "label.rows": "行",
    "label.cols": "列",
    "label.title": "标题",
    "label.slug": "标识",
    "label.provider": "提供商",
    "label.model": "模型",
    "label.agintiCommand": "AgInTi 命令",
    "label.agintiWorkspace": "AgInTi 工作区",
    "label.biorenderUrl": "BioRender MCP URL",
    "label.biorenderEnv": "BioRender 认证环境变量",
    "label.agintiDryRun": "AgInTi 试运行",
    "label.blenderRender": "Blender 渲染",
    "label.openscadExport": "OpenSCAD 导出",
    "label.agintiImage": "AgInTi 图像",
    "label.biorenderMcp": "BioRender MCP",
    "label.targetRegistry": "目标注册表",
    "label.registryTarget": "注册目标",
    "label.targetInstruction": "目标指令",
    "label.dryRun": "试运行",
    "artifact.noneSelected": "未选择",
    "artifact.metaEmpty": "生成的产物会显示在这里。",
    "artifact.previewAlt": "所选产物预览",
    "artifact.noneYet": "暂无产物",
    "artifact.emptyHint": "渲染、导出或生成图形网格。",
    "artifact.noArtifacts": "暂无产物。",
    "link.image": "图像",
    "message.sceneLoaded": "场景已加载。可以请求组件、论文图形网格、OpenSCAD 导出或 BioRender 设置。",
    "message.sceneJsonApplied": "场景 JSON 已应用。",
    "message.backendSettingsSaved": "后端设置已保存。",
    "message.chooseTargetFirst": "请先选择目标并输入指令。",
    "backend.agintiReady": "AgInTi 就绪",
    "backend.agintiMissing": "缺少 AgInTi",
    "backend.bioPresent": "BioRender 密钥存在",
    "backend.bioEnv": "BioRender 密钥来自环境变量",
    "count.elements": "{count} 个元素",
  },
  "zh-Hant": {
    "app.title": "論文圖形工作室",
    "button.reset": "重置",
    "button.figureGrid": "圖形網格",
    "button.render": "渲染",
    "button.dark": "深色",
    "button.light": "淺色",
    "button.send": "發送",
    "button.dispatchTarget": "分發目標",
    "button.saveSettings": "保存設定",
    "button.openBioRender": "打開 BioRender",
    "button.applyJson": "套用 JSON",
    "button.dryRun": "試運行",
    "section.chat": "聊天",
    "section.canvas": "畫布",
    "section.scene": "場景",
    "section.backends": "後端",
    "status.ready": "就緒",
    "status.thinking": "思考中",
    "status.idle": "空閒",
    "status.rendering": "渲染中",
    "status.rendered": "已渲染",
    "status.error": "錯誤",
    "status.loading": "載入中",
    "chip.figure2x3": "圖 2x3",
    "chip.vivid": "鮮明",
    "chip.addLens": "添加透鏡",
    "chip.addFilter": "添加濾光片",
    "placeholder.message": "請求論文裝置、光學平台、設備概念、標籤、顏色或生成圖形面板。",
    "placeholder.targetInstruction": "對任意已配置目標進行試運行指令。",
    "label.prompt": "提示詞",
    "label.rows": "行",
    "label.cols": "列",
    "label.title": "標題",
    "label.slug": "標識",
    "label.provider": "提供商",
    "label.model": "模型",
    "label.agintiCommand": "AgInTi 命令",
    "label.agintiWorkspace": "AgInTi 工作區",
    "label.biorenderUrl": "BioRender MCP URL",
    "label.biorenderEnv": "BioRender 認證環境變數",
    "label.agintiDryRun": "AgInTi 試運行",
    "label.blenderRender": "Blender 渲染",
    "label.openscadExport": "OpenSCAD 匯出",
    "label.agintiImage": "AgInTi 圖像",
    "label.biorenderMcp": "BioRender MCP",
    "label.targetRegistry": "目標註冊表",
    "label.registryTarget": "註冊目標",
    "label.targetInstruction": "目標指令",
    "label.dryRun": "試運行",
    "artifact.noneSelected": "未選擇",
    "artifact.metaEmpty": "生成的產物會顯示在這裡。",
    "artifact.previewAlt": "所選產物預覽",
    "artifact.noneYet": "暫無產物",
    "artifact.emptyHint": "渲染、匯出或生成圖形網格。",
    "artifact.noArtifacts": "暫無產物。",
    "link.image": "圖像",
    "message.sceneLoaded": "場景已載入。可以請求組件、論文圖形網格、OpenSCAD 匯出或 BioRender 設定。",
    "message.sceneJsonApplied": "場景 JSON 已套用。",
    "message.backendSettingsSaved": "後端設定已保存。",
    "message.chooseTargetFirst": "請先選擇目標並輸入指令。",
    "backend.agintiReady": "AgInTi 就緒",
    "backend.agintiMissing": "缺少 AgInTi",
    "backend.bioPresent": "BioRender 密鑰存在",
    "backend.bioEnv": "BioRender 密鑰來自環境變數",
    "count.elements": "{count} 個元素",
  },
  de: {
    "app.title": "Paper Figure Studio",
    "button.reset": "Zurücksetzen",
    "button.figureGrid": "Figurenraster",
    "button.render": "Rendern",
    "button.dark": "Dunkel",
    "button.light": "Hell",
    "button.send": "Senden",
    "button.dispatchTarget": "Ziel senden",
    "button.saveSettings": "Einstellungen speichern",
    "button.openBioRender": "BioRender öffnen",
    "button.applyJson": "JSON anwenden",
    "button.dryRun": "Testlauf",
    "section.chat": "Chat",
    "section.canvas": "Canvas",
    "section.scene": "Szene",
    "section.backends": "Backends",
    "status.ready": "Bereit",
    "status.thinking": "Denkt",
    "status.idle": "Inaktiv",
    "status.rendering": "Rendert",
    "status.rendered": "Gerendert",
    "status.error": "Fehler",
    "status.loading": "Lädt",
    "chip.figure2x3": "Figur 2x3",
    "chip.vivid": "Lebendig",
    "chip.addLens": "Linse hinzufügen",
    "chip.addFilter": "Filter hinzufügen",
    "placeholder.message": "Frage nach Paper-Setup, optischer Bank, Gerätekonzept, Labels, Farben oder Figurenpanels.",
    "placeholder.targetInstruction": "Testlauf-Anweisung für ein konfiguriertes Ziel.",
    "label.prompt": "Prompt",
    "label.rows": "Zeilen",
    "label.cols": "Spalten",
    "label.title": "Titel",
    "label.slug": "Slug",
    "label.provider": "Anbieter",
    "label.model": "Modell",
    "label.agintiCommand": "AgInTi-Befehl",
    "label.agintiWorkspace": "AgInTi-Workspace",
    "label.biorenderUrl": "BioRender MCP URL",
    "label.biorenderEnv": "BioRender Auth-Env",
    "label.agintiDryRun": "AgInTi-Testlauf",
    "label.blenderRender": "Blender-Render",
    "label.openscadExport": "OpenSCAD-Export",
    "label.agintiImage": "AgInTi-Bild",
    "label.biorenderMcp": "BioRender MCP",
    "label.targetRegistry": "Zielregister",
    "label.registryTarget": "Registerziel",
    "label.targetInstruction": "Zielanweisung",
    "label.dryRun": "Testlauf",
    "artifact.noneSelected": "Nichts ausgewählt",
    "artifact.metaEmpty": "Generierte Artefakte erscheinen hier.",
    "artifact.previewAlt": "Vorschau des ausgewählten Artefakts",
    "artifact.noneYet": "Noch kein Artefakt",
    "artifact.emptyHint": "Rendern, exportieren oder Figurenraster erzeugen.",
    "artifact.noArtifacts": "Noch keine Artefakte.",
    "link.image": "Bild",
    "message.sceneLoaded": "Szene geladen. Frage nach Komponenten, Figurenrastern, OpenSCAD-Exporten oder BioRender-Einstellungen.",
    "message.sceneJsonApplied": "Szenen-JSON angewendet.",
    "message.backendSettingsSaved": "Backend-Einstellungen gespeichert.",
    "message.chooseTargetFirst": "Wähle zuerst ein Ziel und gib eine Anweisung ein.",
    "backend.agintiReady": "AgInTi bereit",
    "backend.agintiMissing": "AgInTi fehlt",
    "backend.bioPresent": "BioRender-Schlüssel vorhanden",
    "backend.bioEnv": "BioRender-Schlüssel via env",
    "count.elements": "{count} Elemente",
  },
  ru: {
    "app.title": "Студия Фигур",
    "button.reset": "Сброс",
    "button.figureGrid": "Сетка фигур",
    "button.render": "Рендер",
    "button.dark": "Темная",
    "button.light": "Светлая",
    "button.send": "Отправить",
    "button.dispatchTarget": "Отправить цель",
    "button.saveSettings": "Сохранить настройки",
    "button.openBioRender": "Открыть BioRender",
    "button.applyJson": "Применить JSON",
    "button.dryRun": "Пробный запуск",
    "section.chat": "Чат",
    "section.canvas": "Холст",
    "section.scene": "Сцена",
    "section.backends": "Бэкенды",
    "status.ready": "Готово",
    "status.thinking": "Думает",
    "status.idle": "Ожидание",
    "status.rendering": "Рендеринг",
    "status.rendered": "Готово",
    "status.error": "Ошибка",
    "status.loading": "Загрузка",
    "chip.figure2x3": "Фигура 2x3",
    "chip.vivid": "Ярче",
    "chip.addLens": "Добавить линзу",
    "chip.addFilter": "Добавить фильтр",
    "placeholder.message": "Запросите установку, оптический стенд, концепт устройства, подписи, цвета или панели.",
    "placeholder.targetInstruction": "Пробный запуск инструкции для настроенной цели.",
    "label.prompt": "Промпт",
    "label.rows": "Строки",
    "label.cols": "Колонки",
    "label.title": "Заголовок",
    "label.slug": "Slug",
    "label.provider": "Провайдер",
    "label.model": "Модель",
    "label.agintiCommand": "Команда AgInTi",
    "label.agintiWorkspace": "Рабочая папка AgInTi",
    "label.biorenderUrl": "BioRender MCP URL",
    "label.biorenderEnv": "BioRender auth env",
    "label.agintiDryRun": "AgInTi dry run",
    "label.blenderRender": "Рендер Blender",
    "label.openscadExport": "Экспорт OpenSCAD",
    "label.agintiImage": "Изображение AgInTi",
    "label.biorenderMcp": "BioRender MCP",
    "label.targetRegistry": "Реестр целей",
    "label.registryTarget": "Цель",
    "label.targetInstruction": "Инструкция цели",
    "label.dryRun": "Пробный запуск",
    "artifact.noneSelected": "Ничего не выбрано",
    "artifact.metaEmpty": "Созданные артефакты появятся здесь.",
    "artifact.previewAlt": "Предпросмотр выбранного артефакта",
    "artifact.noneYet": "Артефактов пока нет",
    "artifact.emptyHint": "Сделайте рендер, экспорт или сетку фигур.",
    "artifact.noArtifacts": "Артефактов пока нет.",
    "link.image": "Изображение",
    "message.sceneLoaded": "Сцена загружена. Запросите компоненты, сетки фигур, экспорт OpenSCAD или настройки BioRender.",
    "message.sceneJsonApplied": "JSON сцены применен.",
    "message.backendSettingsSaved": "Настройки бэкенда сохранены.",
    "message.chooseTargetFirst": "Сначала выберите цель и введите инструкцию.",
    "backend.agintiReady": "AgInTi готов",
    "backend.agintiMissing": "AgInTi отсутствует",
    "backend.bioPresent": "Ключ BioRender найден",
    "backend.bioEnv": "Ключ BioRender через env",
    "count.elements": "{count} элементов",
  },
};

const DEFAULT_LOCALE = "en";
let currentLocale = localStorage.getItem("appautoaction-locale") || DEFAULT_LOCALE;

let spec = null;
let settings = null;
let artifacts = [];
let targets = [];
let selectedArtifactId = "";
let rendering = false;

const messages = document.getElementById("messages");
const chatStatus = document.getElementById("chatStatus");
const renderStatus = document.getElementById("renderStatus");
const previewImage = document.getElementById("previewImage");
const emptyPreview = document.getElementById("emptyPreview");
const artifactViewer = document.getElementById("artifactViewer");
const artifactList = document.getElementById("artifactList");
const artifactTitle = document.getElementById("artifactTitle");
const artifactMeta = document.getElementById("artifactMeta");
const artifactKind = document.getElementById("artifactKind");
const specEditor = document.getElementById("specEditor");
const specMeta = document.getElementById("specMeta");
const titleInput = document.getElementById("titleInput");
const slugInput = document.getElementById("slugInput");
const pngLink = document.getElementById("pngLink");
const blendLink = document.getElementById("blendLink");
const specLink = document.getElementById("specLink");
const backendStatus = document.getElementById("backendStatus");
const themeButton = document.getElementById("themeBtn");
const localeSelect = document.getElementById("localeSelect");
const targetSelect = document.getElementById("targetSelect");
const targetInstruction = document.getElementById("targetInstruction");

setupLocale();
init();

async function init() {
  const [specResponse] = await Promise.all([fetch("/api/spec"), loadSettings(), loadTargets(), loadArtifacts()]);
  const data = await specResponse.json();
  spec = data.spec;
  syncSpecView();
  if (data.preview_url && !artifacts.length) {
    showPreview(data.preview_url);
  }
  addMessage("assistant", t("message.sceneLoaded"));
}

document.getElementById("chatForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = document.getElementById("messageInput");
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  addMessage("user", text);
  chatStatus.textContent = t("status.thinking");
  try {
    const data = await postJson("/api/chat", { message: text, spec });
    if (!data.ok) throw new Error(data.error || "Chat failed");
    spec = data.spec;
    syncSpecView();
    if (data.artifacts) {
      setArtifacts(data.artifacts);
    }
    addMessage("assistant", data.reply);
  } catch (error) {
    addMessage("assistant", error.message);
  } finally {
    chatStatus.textContent = t("status.ready");
  }
});

document.querySelectorAll("[data-prompt]").forEach((button) => {
  button.addEventListener("click", () => {
    document.getElementById("messageInput").value = button.dataset.prompt;
    document.getElementById("chatForm").requestSubmit();
  });
});

document.getElementById("renderBtn").addEventListener("click", renderScene);
document.getElementById("dryRunBtn").addEventListener("click", dryRunScene);
document.getElementById("figureBtn").addEventListener("click", generateFigureGrid);
document.getElementById("openscadBtn").addEventListener("click", exportOpenScad);
document.getElementById("templateBtn").addEventListener("click", init);
document.getElementById("dispatchTargetBtn").addEventListener("click", dispatchRegistryTarget);
themeButton.addEventListener("click", toggleTheme);
localeSelect.addEventListener("change", () => applyLocale(localeSelect.value, true));
document.getElementById("openBioRenderBtn").addEventListener("click", () => {
  const url = document.getElementById("biorenderUrl").value.trim() || "https://app.biorender.com/";
  window.open(url.includes("/mcp") ? "https://app.biorender.com/" : url, "_blank", "noopener");
});

document.getElementById("applySpecBtn").addEventListener("click", () => {
  try {
    spec = JSON.parse(specEditor.value);
    syncSpecView();
    addMessage("assistant", t("message.sceneJsonApplied"));
  } catch (error) {
    addMessage("assistant", `JSON error: ${error.message}`);
  }
});

document.getElementById("settingsForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const nextSettings = collectSettings();
  try {
    const data = await postJson("/api/settings", { settings: nextSettings });
    settings = data.settings;
    syncSettingsView(data.status);
    addMessage("assistant", t("message.backendSettingsSaved"));
  } catch (error) {
    addMessage("assistant", error.message);
  }
});

titleInput.addEventListener("change", () => {
  spec.title = titleInput.value.trim() || spec.title;
  syncSpecView();
});

slugInput.addEventListener("change", () => {
  spec.slug = slugInput.value.trim() || spec.slug;
  syncSpecView();
});

async function renderScene() {
  if (rendering) return;
  rendering = true;
  setRenderBusy(true, t("status.rendering"));
  try {
    const data = await postJson("/api/render", { spec });
    if (!data.ok) throw new Error(data.error || "Render failed");
    setLink(pngLink, data.image_url);
    setLink(blendLink, data.blend_url);
    setLink(specLink, data.spec_url);
    setArtifacts(data.artifacts);
    renderStatus.textContent = t("status.rendered");
    addMessage("assistant", interpolate(t("message.rendered"), { title: data.plan.title }));
  } catch (error) {
    renderStatus.textContent = t("status.error");
    addMessage("assistant", error.message);
  } finally {
    rendering = false;
    setRenderBusy(false);
  }
}

async function dryRunScene() {
  try {
    const data = await postJson("/api/plan", { spec });
    if (!data.ok) throw new Error(data.error || "Dry run failed");
    addMessage("assistant", interpolate(t("message.planOk"), { path: data.plan.png }));
    renderStatus.textContent = t("status.planOk");
  } catch (error) {
    renderStatus.textContent = t("status.planError");
    addMessage("assistant", error.message);
  }
}

async function generateFigureGrid() {
  renderStatus.textContent = t("status.generatingGrid");
  const payload = {
    prompt: document.getElementById("figurePrompt").value.trim(),
    rows: Number(document.getElementById("figureRows").value || 2),
    cols: Number(document.getElementById("figureCols").value || 3),
  };
  try {
    const data = await postJson("/api/figure-grid", payload);
    if (!data.ok) throw new Error(data.error || "Figure grid failed");
    setArtifacts(data.artifacts);
    setLink(pngLink, data.figure_url);
    const agintiSummary = data.aginti?.summary ? ` AgInTi: ${data.aginti.summary}` : "";
    addMessage("assistant", `${interpolate(t("message.gridGenerated"), { rows: data.rows, cols: data.cols })}${agintiSummary}`);
    renderStatus.textContent = t("status.gridReady");
  } catch (error) {
    renderStatus.textContent = t("status.gridError");
    addMessage("assistant", error.message);
  }
}

async function exportOpenScad() {
  renderStatus.textContent = t("status.exportingCad");
  try {
    const data = await postJson("/api/openscad-export", { spec });
    if (!data.ok) throw new Error(data.error || "OpenSCAD export failed");
    setArtifacts(data.artifacts);
    addMessage("assistant", interpolate(t("message.exportedOpenScad"), { path: data.export.path }));
    renderStatus.textContent = t("status.cadReady");
  } catch (error) {
    renderStatus.textContent = t("status.cadError");
    addMessage("assistant", error.message);
  }
}

async function loadSettings() {
  const response = await fetch("/api/settings");
  const data = await response.json();
  settings = data.settings;
  syncSettingsView(data.status);
}

async function loadArtifacts() {
  const response = await fetch("/api/artifacts");
  const data = await response.json();
  setArtifacts(data);
}

async function loadTargets() {
  const response = await fetch("/api/targets");
  const data = await response.json();
  targets = Array.isArray(data.targets) ? data.targets : [];
  renderTargetOptions();
}

async function dispatchRegistryTarget() {
  const target = targetSelect.value;
  const instruction = targetInstruction.value.trim();
  if (!target || !instruction) {
    addMessage("assistant", t("message.chooseTargetFirst"));
    return;
  }
  renderStatus.textContent = t("status.dispatching");
  try {
    const data = await postJson("/api/dispatch", {
      target,
      instruction,
      dry_run: document.getElementById("dispatchDryRun").checked,
    });
    setArtifacts(data.artifacts);
    const status = data.dispatch?.status || "done";
    addMessage("assistant", interpolate(t("message.targetDispatch"), { status, target }));
    renderStatus.textContent = t("status.dispatchReady");
  } catch (error) {
    renderStatus.textContent = t("status.dispatchError");
    addMessage("assistant", error.message);
  }
}

function renderTargetOptions() {
  targetSelect.innerHTML = "";
  targets.forEach((target) => {
    const option = document.createElement("option");
    option.value = target.name;
    option.textContent = `${target.name} (${target.transport})`;
    option.disabled = !target.enabled;
    targetSelect.appendChild(option);
  });
  if (targets.length && !targetInstruction.value) {
    targetInstruction.value = "Prepare a paper figure workflow for this target";
  }
}

function setArtifacts(bundle) {
  artifacts = Array.isArray(bundle?.items) ? bundle.items : [];
  selectedArtifactId = bundle?.selected_id || artifacts.find((item) => item.selected)?.id || selectedArtifactId;
  renderArtifactList();
  const selected = artifacts.find((item) => item.id === selectedArtifactId) || artifacts[0];
  if (selected) selectArtifact(selected.id);
}

function renderArtifactList() {
  artifactList.innerHTML = "";
  if (!artifacts.length) {
    const empty = document.createElement("p");
    empty.className = "status artifact-empty";
    empty.textContent = t("artifact.noArtifacts");
    artifactList.appendChild(empty);
    return;
  }
  artifacts.forEach((item) => {
    const button = document.createElement("button");
    button.className = "artifact-item";
    button.type = "button";
    button.dataset.selected = item.id === selectedArtifactId ? "true" : "false";
    button.addEventListener("click", () => selectArtifact(item.id));

    const top = document.createElement("span");
    top.className = "artifact-item-top";
    const title = document.createElement("strong");
    title.textContent = item.title;
    const kind = document.createElement("span");
    kind.textContent = item.kind;
    top.append(title, kind);

    const meta = document.createElement("small");
    meta.textContent = item.source || item.path;
    const preview = document.createElement("em");
    preview.textContent = item.preview || item.path;
    button.append(top, meta, preview);
    artifactList.appendChild(button);
  });
}

async function selectArtifact(id) {
  selectedArtifactId = id;
  renderArtifactList();
  const item = artifacts.find((candidate) => candidate.id === id);
  if (!item) return;
  artifactTitle.textContent = item.title;
  artifactMeta.textContent = item.path;
  artifactKind.textContent = item.kind;
  if (item.kind === "image") {
    resetViewer();
    showPreview(item.url);
    setLink(pngLink, item.url);
    return;
  }
  resetViewer();
  previewImage.hidden = true;
  emptyPreview.hidden = true;
  const body = document.createElement("pre");
  body.className = "text-artifact";
  if (["json", "text", "openscad"].includes(item.kind)) {
    const response = await fetch(item.url);
    body.textContent = await response.text();
  } else {
    body.textContent = `${t("artifact.path")}: ${item.path}`;
  }
  artifactViewer.appendChild(body);
}

function syncSpecView() {
  titleInput.value = spec.title || "";
  slugInput.value = spec.slug || "";
  specEditor.value = JSON.stringify(spec, null, 2);
  const count = Array.isArray(spec.elements) ? spec.elements.length : 0;
  specMeta.textContent = interpolate(t("count.elements"), { count });
}

function syncSettingsView(status = {}) {
  if (!settings) return;
  document.getElementById("agintiCommand").value = settings.aginti?.command || "aginti";
  document.getElementById("agintiWorkspace").value = settings.aginti?.workspace || "../Agent/AgInTiFlow";
  document.getElementById("agintiProvider").value = settings.aginti?.image_provider || "grsai";
  document.getElementById("agintiModel").value = settings.aginti?.image_model || "nano-banana-2";
  document.getElementById("agintiDryRun").checked = Boolean(settings.aginti?.dry_run);
  document.getElementById("biorenderUrl").value = settings.biorender?.mcp_url || "https://mcp.services.biorender.com/mcp";
  document.getElementById("biorenderEnv").value = settings.biorender?.auth_env || "BIORENDER_API_KEY";
  document.getElementById("toolBlender").checked = settings.toolchain?.blender !== false;
  document.getElementById("toolOpenScad").checked = settings.toolchain?.openscad !== false;
  document.getElementById("toolAgintiImage").checked = settings.toolchain?.aginti_image !== false;
  document.getElementById("toolBioRender").checked = Boolean(settings.toolchain?.biorender);
  document.getElementById("toolTargetRegistry").checked = settings.toolchain?.target_registry !== false;
  const agintiReady = status.aginti?.command_path ? t("backend.agintiReady") : t("backend.agintiMissing");
  const bioReady = status.biorender?.auth_env_present ? t("backend.bioPresent") : t("backend.bioEnv");
  backendStatus.textContent = `${agintiReady} · ${bioReady}`;
  syncThemeButton();
}

function collectSettings() {
  return {
    ...settings,
    aginti: {
      ...settings.aginti,
      command: document.getElementById("agintiCommand").value.trim() || "aginti",
      workspace: document.getElementById("agintiWorkspace").value.trim() || "../Agent/AgInTiFlow",
      image_provider: document.getElementById("agintiProvider").value.trim() || "grsai",
      image_model: document.getElementById("agintiModel").value.trim() || "nano-banana-2",
      dry_run: document.getElementById("agintiDryRun").checked,
    },
    biorender: {
      ...settings.biorender,
      mcp_url: document.getElementById("biorenderUrl").value.trim() || "https://mcp.services.biorender.com/mcp",
      auth_env: document.getElementById("biorenderEnv").value.trim() || "BIORENDER_API_KEY",
    },
    toolchain: {
      ...settings.toolchain,
      blender: document.getElementById("toolBlender").checked,
      openscad: document.getElementById("toolOpenScad").checked,
      aginti_image: document.getElementById("toolAgintiImage").checked,
      biorender: document.getElementById("toolBioRender").checked,
      target_registry: document.getElementById("toolTargetRegistry").checked,
    },
  };
}

function toggleTheme() {
  const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  localStorage.setItem("appautoaction-theme", next);
  syncThemeButton();
}

function syncThemeButton() {
  const isDark = document.documentElement.dataset.theme === "dark";
  themeButton.textContent = isDark ? t("button.light") : t("button.dark");
  themeButton.setAttribute("aria-label", isDark ? t("aria.switchLight") : t("aria.switchDark"));
}

function addMessage(role, text) {
  const item = document.createElement("div");
  item.className = `message ${role}`;
  item.textContent = text;
  messages.appendChild(item);
  messages.scrollTop = messages.scrollHeight;
}

function setupLocale() {
  if (!TRANSLATIONS[currentLocale]) {
    currentLocale = DEFAULT_LOCALE;
  }
  localeSelect.value = currentLocale;
  applyLocale(currentLocale, false);
}

function applyLocale(nextLocale, persist) {
  currentLocale = TRANSLATIONS[nextLocale] ? nextLocale : DEFAULT_LOCALE;
  document.documentElement.lang = currentLocale;
  localeSelect.value = currentLocale;
  if (persist) {
    localStorage.setItem("appautoaction-locale", currentLocale);
  }
  document.querySelectorAll("[data-i18n]").forEach((node) => {
    node.textContent = t(node.dataset.i18n);
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((node) => {
    node.setAttribute("placeholder", t(node.dataset.i18nPlaceholder));
  });
  document.querySelectorAll("[data-i18n-alt]").forEach((node) => {
    node.setAttribute("alt", t(node.dataset.i18nAlt));
  });
  syncThemeButton();
  if (spec) {
    syncSpecView();
  }
  if (settings) {
    syncSettingsView();
  }
  if (!artifacts.length) {
    renderArtifactList();
  }
}

function t(key) {
  return TRANSLATIONS[currentLocale]?.[key] || TRANSLATIONS[DEFAULT_LOCALE][key] || key;
}

function interpolate(template, values) {
  return template.replace(/\{(\w+)\}/g, (_, key) => String(values[key] ?? ""));
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || response.statusText);
  return data;
}

function showPreview(url) {
  previewImage.onload = () => {
    previewImage.hidden = false;
    emptyPreview.hidden = true;
  };
  previewImage.src = url;
}

function resetViewer() {
  [...artifactViewer.querySelectorAll(".text-artifact")].forEach((node) => node.remove());
  emptyPreview.hidden = false;
}

function setLink(link, url) {
  link.href = url;
  link.hidden = false;
}

function setRenderBusy(isBusy, label = t("status.idle")) {
  document.getElementById("renderBtn").disabled = isBusy;
  if (isBusy || label !== t("status.idle")) {
    renderStatus.textContent = label;
  }
}
