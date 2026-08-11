#!/usr/bin/env python3
# ckbcomp -- translate XKB layout to loadkeys or kbdcontrol format
# Python 3 port of the original Perl ckbcomp (byte-identical output).
# Copyright (C) 2005,2006 Anton Zinoviev. GPL v2+ (see original).

# ==================== GENERATED DATA (verbatim from Perl) ====================
# ---- BEGIN GENERATED DATA (extracted verbatim from the original Perl ckbcomp via
#      a Perl->JSON dump, so every entry is byte-identical to upstream). ----

XKBSYM_TABLE_BASE = {
    '0': '0030',
    '1': '0031',
    '2': '0032',
    '3': '0033',
    '4': '0034',
    '5': '0035',
    '6': '0036',
    '7': '0037',
    '8': '0038',
    '9': '0039',
    'A': '0041',
    'AE': '00c6',
    'Aacute': '00c1',
    'Abelowdot': '1ea0',
    'Abreve': '0102',
    'Abreveacute': '1eae',
    'Abrevebelowdot': '1eb6',
    'Abrevegrave': '1eb0',
    'Abrevehook': '1eb2',
    'Abrevetilde': '1eb4',
    'Acircumflex': '00c2',
    'Acircumflexacute': '1ea4',
    'Acircumflexbelowdot': '1eac',
    'Acircumflexgrave': '1ea6',
    'Acircumflexhook': '1ea8',
    'Acircumflextilde': '1eaa',
    'Adiaeresis': '00c4',
    'Agrave': '00c0',
    'Ahook': '1ea2',
    'Amacron': '0100',
    'Aogonek': '0104',
    'Arabic_0': '0660',
    'Arabic_1': '0661',
    'Arabic_2': '0662',
    'Arabic_3': '0663',
    'Arabic_4': '0664',
    'Arabic_5': '0665',
    'Arabic_6': '0666',
    'Arabic_7': '0667',
    'Arabic_8': '0668',
    'Arabic_9': '0669',
    'Arabic_ain': '0639',
    'Arabic_alef': '0627',
    'Arabic_alefmaksura': '0649',
    'Arabic_beh': '0628',
    'Arabic_comma': '060c',
    'Arabic_dad': '0636',
    'Arabic_dal': '062f',
    'Arabic_damma': '064f',
    'Arabic_dammatan': '064c',
    'Arabic_ddal': '0688',
    'Arabic_farsi_yeh': '06cc',
    'Arabic_fatha': '064e',
    'Arabic_fathatan': '064b',
    'Arabic_feh': '0641',
    'Arabic_fullstop': '06d4',
    'Arabic_gaf': '06af',
    'Arabic_ghain': '063a',
    'Arabic_ha': '0647',
    'Arabic_hah': '062d',
    'Arabic_hamza': '0621',
    'Arabic_hamza_above': '0654',
    'Arabic_hamza_below': '0655',
    'Arabic_hamzaonalef': '0623',
    'Arabic_hamzaonwaw': '0624',
    'Arabic_hamzaonyeh': '0626',
    'Arabic_hamzaunderalef': '0625',
    'Arabic_heh': '0647',
    'Arabic_heh_doachashmee': '06be',
    'Arabic_heh_goal': '06c1',
    'Arabic_jeem': '062c',
    'Arabic_jeh': '0698',
    'Arabic_kaf': '0643',
    'Arabic_kasra': '0650',
    'Arabic_kasratan': '064d',
    'Arabic_keheh': '06a9',
    'Arabic_khah': '062e',
    'Arabic_lam': '0644',
    'Arabic_madda_above': '0653',
    'Arabic_maddaonalef': '0622',
    'Arabic_meem': '0645',
    'Arabic_noon': '0646',
    'Arabic_noon_ghunna': '06ba',
    'Arabic_peh': '067e',
    'Arabic_percent': '066a',
    'Arabic_qaf': '0642',
    'Arabic_question_mark': '061f',
    'Arabic_ra': '0631',
    'Arabic_rreh': '0691',
    'Arabic_sad': '0635',
    'Arabic_seen': '0633',
    'Arabic_semicolon': '061b',
    'Arabic_shadda': '0651',
    'Arabic_sheen': '0634',
    'Arabic_sukun': '0652',
    'Arabic_superscript_alef': '0670',
    'Arabic_tah': '0637',
    'Arabic_tatweel': '0640',
    'Arabic_tcheh': '0686',
    'Arabic_teh': '062a',
    'Arabic_tehmarbuta': '0629',
    'Arabic_thal': '0630',
    'Arabic_theh': '062b',
    'Arabic_tteh': '0679',
    'Arabic_veh': '06a4',
    'Arabic_waw': '0648',
    'Arabic_yeh': '064a',
    'Arabic_yeh_baree': '06d2',
    'Arabic_zah': '0638',
    'Arabic_zain': '0632',
    'Aring': '00c5',
    'Armenian_AT': '0538',
    'Armenian_AYB': '0531',
    'Armenian_BEN': '0532',
    'Armenian_CHA': '0549',
    'Armenian_DA': '0534',
    'Armenian_DZA': '0541',
    'Armenian_E': '0537',
    'Armenian_FE': '0556',
    'Armenian_GHAT': '0542',
    'Armenian_GIM': '0533',
    'Armenian_HI': '0545',
    'Armenian_HO': '0540',
    'Armenian_INI': '053b',
    'Armenian_JE': '054b',
    'Armenian_KE': '0554',
    'Armenian_KEN': '053f',
    'Armenian_KHE': '053d',
    'Armenian_LYUN': '053c',
    'Armenian_MEN': '0544',
    'Armenian_NU': '0546',
    'Armenian_O': '0555',
    'Armenian_PE': '054a',
    'Armenian_PYUR': '0553',
    'Armenian_RA': '054c',
    'Armenian_RE': '0550',
    'Armenian_SE': '054d',
    'Armenian_SHA': '0547',
    'Armenian_TCHE': '0543',
    'Armenian_TO': '0539',
    'Armenian_TSA': '053e',
    'Armenian_TSO': '0551',
    'Armenian_TYUN': '054f',
    'Armenian_VEV': '054e',
    'Armenian_VO': '0548',
    'Armenian_VYUN': '0552',
    'Armenian_YECH': '0535',
    'Armenian_ZA': '0536',
    'Armenian_ZHE': '053a',
    'Armenian_accent': '055b',
    'Armenian_amanak': '055c',
    'Armenian_apostrophe': '055a',
    'Armenian_at': '0568',
    'Armenian_ayb': '0561',
    'Armenian_ben': '0562',
    'Armenian_but': '055d',
    'Armenian_cha': '0579',
    'Armenian_da': '0564',
    'Armenian_dza': '0571',
    'Armenian_e': '0567',
    'Armenian_exclam': '055c',
    'Armenian_fe': '0586',
    'Armenian_full_stop': '0589',
    'Armenian_ghat': '0572',
    'Armenian_gim': '0563',
    'Armenian_hi': '0575',
    'Armenian_ho': '0570',
    'Armenian_hyphen': '058a',
    'Armenian_ini': '056b',
    'Armenian_je': '057b',
    'Armenian_ke': '0584',
    'Armenian_ken': '056f',
    'Armenian_khe': '056d',
    'Armenian_ligature_ew': '0587',
    'Armenian_lyun': '056c',
    'Armenian_men': '0574',
    'Armenian_nu': '0576',
    'Armenian_o': '0585',
    'Armenian_paruyk': '055e',
    'Armenian_pe': '057a',
    'Armenian_pyur': '0583',
    'Armenian_question': '055e',
    'Armenian_ra': '057c',
    'Armenian_re': '0580',
    'Armenian_se': '057d',
    'Armenian_separation_mark': '055d',
    'Armenian_sha': '0577',
    'Armenian_shesht': '055b',
    'Armenian_tche': '0573',
    'Armenian_to': '0569',
    'Armenian_tsa': '056e',
    'Armenian_tso': '0581',
    'Armenian_tyun': '057f',
    'Armenian_verjaket': '0589',
    'Armenian_vev': '057e',
    'Armenian_vo': '0578',
    'Armenian_vyun': '0582',
    'Armenian_yech': '0565',
    'Armenian_yentamna': '058a',
    'Armenian_za': '0566',
    'Armenian_zhe': '056a',
    'Atilde': '00c3',
    'B': '0042',
    'Babovedot': '1e02',
    'Byelorussian_SHORTU': '040e',
    'Byelorussian_shortu': '045e',
    'C': '0043',
    'Cabovedot': '010a',
    'Cacute': '0106',
    'Ccaron': '010c',
    'Ccedilla': '00c7',
    'Ccircumflex': '0108',
    'ColonSign': '20a1',
    'CruzeiroSign': '20a2',
    'Cyrillic_A': '0410',
    'Cyrillic_BE': '0411',
    'Cyrillic_CHE': '0427',
    'Cyrillic_CHE_descender': '04b6',
    'Cyrillic_CHE_vertstroke': '04b8',
    'Cyrillic_DE': '0414',
    'Cyrillic_DZHE': '040f',
    'Cyrillic_E': '042d',
    'Cyrillic_EF': '0424',
    'Cyrillic_EL': '041b',
    'Cyrillic_EM': '041c',
    'Cyrillic_EN': '041d',
    'Cyrillic_EN_descender': '04a2',
    'Cyrillic_ER': '0420',
    'Cyrillic_ES': '0421',
    'Cyrillic_F': '0424',
    'Cyrillic_GHE': '0413',
    'Cyrillic_GHE_bar': '0492',
    'Cyrillic_HA': '0425',
    'Cyrillic_HARDSIGN': '042a',
    'Cyrillic_HA_descender': '04b2',
    'Cyrillic_I': '0418',
    'Cyrillic_IE': '0415',
    'Cyrillic_IO': '0401',
    'Cyrillic_I_macron': '04e2',
    'Cyrillic_JE': '0408',
    'Cyrillic_KA': '041a',
    'Cyrillic_KA_descender': '049a',
    'Cyrillic_KA_vertstroke': '049c',
    'Cyrillic_LJE': '0409',
    'Cyrillic_N': '041d',
    'Cyrillic_NJE': '040a',
    'Cyrillic_O': '041e',
    'Cyrillic_O_bar': '04e8',
    'Cyrillic_PE': '041f',
    'Cyrillic_SCHWA': '04d8',
    'Cyrillic_SHA': '0428',
    'Cyrillic_SHCHA': '0429',
    'Cyrillic_SHHA': '04ba',
    'Cyrillic_SHORTI': '0419',
    'Cyrillic_SOFTSIGN': '042c',
    'Cyrillic_TE': '0422',
    'Cyrillic_TSE': '0426',
    'Cyrillic_U': '0423',
    'Cyrillic_UI': '042b',
    'Cyrillic_U_macron': '04ee',
    'Cyrillic_U_straight': '04ae',
    'Cyrillic_U_straight_bar': '04b0',
    'Cyrillic_VE': '0412',
    'Cyrillic_YA': '042f',
    'Cyrillic_YERU': '042b',
    'Cyrillic_YU': '042e',
    'Cyrillic_ZE': '0417',
    'Cyrillic_ZH': '0416',
    'Cyrillic_ZHE': '0416',
    'Cyrillic_ZHE_descender': '0496',
    'Cyrillic_a': '0430',
    'Cyrillic_be': '0431',
    'Cyrillic_che': '0447',
    'Cyrillic_che_descender': '04b7',
    'Cyrillic_che_vertstroke': '04b9',
    'Cyrillic_de': '0434',
    'Cyrillic_dzhe': '045f',
    'Cyrillic_e': '044d',
    'Cyrillic_ef': '0444',
    'Cyrillic_el': '043b',
    'Cyrillic_em': '043c',
    'Cyrillic_en': '043d',
    'Cyrillic_en_descender': '04a3',
    'Cyrillic_er': '0440',
    'Cyrillic_es': '0441',
    'Cyrillic_f': '0444',
    'Cyrillic_ghe': '0433',
    'Cyrillic_ghe_bar': '0493',
    'Cyrillic_ha': '0445',
    'Cyrillic_ha_descender': '04b3',
    'Cyrillic_hardsign': '044a',
    'Cyrillic_i': '0438',
    'Cyrillic_i_macron': '04e3',
    'Cyrillic_ie': '0435',
    'Cyrillic_io': '0451',
    'Cyrillic_je': '0458',
    'Cyrillic_ka': '043a',
    'Cyrillic_ka_descender': '049b',
    'Cyrillic_ka_vertstroke': '049d',
    'Cyrillic_lje': '0459',
    'Cyrillic_n': '043d',
    'Cyrillic_nje': '045a',
    'Cyrillic_o': '043e',
    'Cyrillic_o_bar': '04e9',
    'Cyrillic_pe': '043f',
    'Cyrillic_schwa': '04d9',
    'Cyrillic_sha': '0448',
    'Cyrillic_shcha': '0449',
    'Cyrillic_shha': '04bb',
    'Cyrillic_shorti': '0439',
    'Cyrillic_softsign': '044c',
    'Cyrillic_te': '0442',
    'Cyrillic_tse': '0446',
    'Cyrillic_u': '0443',
    'Cyrillic_u_macron': '04ef',
    'Cyrillic_u_straight': '04af',
    'Cyrillic_u_straight_bar': '04b1',
    'Cyrillic_ui': '044b',
    'Cyrillic_ve': '0432',
    'Cyrillic_ya': '044f',
    'Cyrillic_yeru': '044b',
    'Cyrillic_yu': '044e',
    'Cyrillic_ze': '0437',
    'Cyrillic_zh': '0436',
    'Cyrillic_zhe': '0436',
    'Cyrillic_zhe_descender': '0497',
    'D': '0044',
    'Dabovedot': '1e0a',
    'Dcaron': '010e',
    'DongSign': '20ab',
    'Dstroke': '0110',
    'E': '0045',
    'ENG': '014a',
    'ETH': '00d0',
    'EZH': '01b7',
    'Eabovedot': '0116',
    'Eacute': '00c9',
    'Ebelowdot': '1eb8',
    'Ecaron': '011a',
    'Ecircumflex': '00ca',
    'Ecircumflexacute': '1ebe',
    'Ecircumflexbelowdot': '1ec6',
    'Ecircumflexgrave': '1ec0',
    'Ecircumflexhook': '1ec2',
    'Ecircumflextilde': '1ec4',
    'EcuSign': '20a0',
    'Ediaeresis': '00cb',
    'Egrave': '00c8',
    'Ehook': '1eba',
    'Emacron': '0112',
    'Eogonek': '0118',
    'Eth': '00d0',
    'Etilde': '1ebc',
    'Euro': '20ac',
    'EuroSign': '20ac',
    'Ezh': '01b7',
    'F': '0046',
    'FFrancSign': '20a3',
    'Fabovedot': '1e1e',
    'Farsi_0': '06f0',
    'Farsi_1': '06f1',
    'Farsi_2': '06f2',
    'Farsi_3': '06f3',
    'Farsi_4': '06f4',
    'Farsi_5': '06f5',
    'Farsi_6': '06f6',
    'Farsi_7': '06f7',
    'Farsi_8': '06f8',
    'Farsi_9': '06f9',
    'Farsi_yeh': '06cc',
    'G': '0047',
    'Gabovedot': '0120',
    'Gbreve': '011e',
    'Gcaron': '01e6',
    'Gcedilla': '0122',
    'Gcircumflex': '011c',
    'Georgian_an': '10d0',
    'Georgian_ban': '10d1',
    'Georgian_can': '10ea',
    'Georgian_char': '10ed',
    'Georgian_chin': '10e9',
    'Georgian_cil': '10ec',
    'Georgian_don': '10d3',
    'Georgian_en': '10d4',
    'Georgian_fi': '10f6',
    'Georgian_gan': '10d2',
    'Georgian_ghan': '10e6',
    'Georgian_hae': '10f0',
    'Georgian_har': '10f4',
    'Georgian_he': '10f1',
    'Georgian_hie': '10f2',
    'Georgian_hoe': '10f5',
    'Georgian_in': '10d8',
    'Georgian_jhan': '10ef',
    'Georgian_jil': '10eb',
    'Georgian_kan': '10d9',
    'Georgian_khar': '10e5',
    'Georgian_las': '10da',
    'Georgian_man': '10db',
    'Georgian_nar': '10dc',
    'Georgian_on': '10dd',
    'Georgian_par': '10de',
    'Georgian_phar': '10e4',
    'Georgian_qar': '10e7',
    'Georgian_rae': '10e0',
    'Georgian_san': '10e1',
    'Georgian_shin': '10e8',
    'Georgian_tan': '10d7',
    'Georgian_tar': '10e2',
    'Georgian_un': '10e3',
    'Georgian_vin': '10d5',
    'Georgian_we': '10f3',
    'Georgian_xan': '10ee',
    'Georgian_zen': '10d6',
    'Georgian_zhar': '10df',
    'Greek_ALPHA': '0391',
    'Greek_ALPHAaccent': '0386',
    'Greek_BETA': '0392',
    'Greek_CHI': '03a7',
    'Greek_DELTA': '0394',
    'Greek_EPSILON': '0395',
    'Greek_EPSILONaccent': '0388',
    'Greek_ETA': '0397',
    'Greek_ETAaccent': '0389',
    'Greek_GAMMA': '0393',
    'Greek_IOTA': '0399',
    'Greek_IOTAaccent': '038a',
    'Greek_IOTAdiaeresis': '03aa',
    'Greek_KAPPA': '039a',
    'Greek_LAMBDA': '039b',
    'Greek_LAMDA': '039b',
    'Greek_MU': '039c',
    'Greek_NU': '039d',
    'Greek_OMEGA': '03a9',
    'Greek_OMEGAaccent': '038f',
    'Greek_OMICRON': '039f',
    'Greek_OMICRONaccent': '038c',
    'Greek_PHI': '03a6',
    'Greek_PI': '03a0',
    'Greek_PSI': '03a8',
    'Greek_RHO': '03a1',
    'Greek_SIGMA': '03a3',
    'Greek_TAU': '03a4',
    'Greek_THETA': '0398',
    'Greek_UPSILON': '03a5',
    'Greek_UPSILONaccent': '038e',
    'Greek_UPSILONdieresis': '03ab',
    'Greek_XI': '039e',
    'Greek_ZETA': '0396',
    'Greek_accentdieresis': '0385',
    'Greek_alpha': '03b1',
    'Greek_alphaaccent': '03ac',
    'Greek_beta': '03b2',
    'Greek_chi': '03c7',
    'Greek_delta': '03b4',
    'Greek_epsilon': '03b5',
    'Greek_epsilonaccent': '03ad',
    'Greek_eta': '03b7',
    'Greek_etaaccent': '03ae',
    'Greek_finalsmallsigma': '03c2',
    'Greek_gamma': '03b3',
    'Greek_horizbar': '2015',
    'Greek_iota': '03b9',
    'Greek_iotaaccent': '03af',
    'Greek_iotaaccentdieresis': '0390',
    'Greek_iotadieresis': '03ca',
    'Greek_kappa': '03ba',
    'Greek_lambda': '03bb',
    'Greek_lamda': '03bb',
    'Greek_mu': '03bc',
    'Greek_nu': '03bd',
    'Greek_omega': '03c9',
    'Greek_omegaaccent': '03ce',
    'Greek_omicron': '03bf',
    'Greek_omicronaccent': '03cc',
    'Greek_phi': '03c6',
    'Greek_pi': '03c0',
    'Greek_psi': '03c8',
    'Greek_rho': '03c1',
    'Greek_sigma': '03c3',
    'Greek_tau': '03c4',
    'Greek_theta': '03b8',
    'Greek_upsilon': '03c5',
    'Greek_upsilonaccent': '03cd',
    'Greek_upsilonaccentdieresis': '03b0',
    'Greek_upsilondieresis': '03cb',
    'Greek_xi': '03be',
    'Greek_zeta': '03b6',
    'H': '0048',
    'Hangul_A': '314f',
    'Hangul_AE': '3150',
    'Hangul_AraeA': '318d',
    'Hangul_AraeAE': '318e',
    'Hangul_Cieuc': '314a',
    'Hangul_Dikeud': '3137',
    'Hangul_E': '3154',
    'Hangul_EO': '3153',
    'Hangul_EU': '3161',
    'Hangul_Hieuh': '314e',
    'Hangul_I': '3163',
    'Hangul_Ieung': '3147',
    'Hangul_J_Cieuc': '11be',
    'Hangul_J_Dikeud': '11ae',
    'Hangul_J_Hieuh': '11c2',
    'Hangul_J_Ieung': '11bc',
    'Hangul_J_Jieuj': '11bd',
    'Hangul_J_Khieuq': '11bf',
    'Hangul_J_Kiyeog': '11a8',
    'Hangul_J_KiyeogSios': '11aa',
    'Hangul_J_KkogjiDalrinIeung': '11f0',
    'Hangul_J_Mieum': '11b7',
    'Hangul_J_Nieun': '11ab',
    'Hangul_J_NieunHieuh': '11ad',
    'Hangul_J_NieunJieuj': '11ac',
    'Hangul_J_PanSios': '11eb',
    'Hangul_J_Phieuf': '11c1',
    'Hangul_J_Pieub': '11b8',
    'Hangul_J_PieubSios': '11b9',
    'Hangul_J_Rieul': '11af',
    'Hangul_J_RieulHieuh': '11b6',
    'Hangul_J_RieulKiyeog': '11b0',
    'Hangul_J_RieulMieum': '11b1',
    'Hangul_J_RieulPhieuf': '11b5',
    'Hangul_J_RieulPieub': '11b2',
    'Hangul_J_RieulSios': '11b3',
    'Hangul_J_RieulTieut': '11b4',
    'Hangul_J_Sios': '11ba',
    'Hangul_J_SsangKiyeog': '11a9',
    'Hangul_J_SsangSios': '11bb',
    'Hangul_J_Tieut': '11c0',
    'Hangul_J_YeorinHieuh': '11f9',
    'Hangul_Jieuj': '3148',
    'Hangul_Khieuq': '314b',
    'Hangul_Kiyeog': '3131',
    'Hangul_KiyeogSios': '3133',
    'Hangul_KkogjiDalrinIeung': '3181',
    'Hangul_Mieum': '3141',
    'Hangul_Nieun': '3134',
    'Hangul_NieunHieuh': '3136',
    'Hangul_NieunJieuj': '3135',
    'Hangul_O': '3157',
    'Hangul_OE': '315a',
    'Hangul_PanSios': '317f',
    'Hangul_Phieuf': '314d',
    'Hangul_Pieub': '3142',
    'Hangul_PieubSios': '3144',
    'Hangul_Rieul': '3139',
    'Hangul_RieulHieuh': '3140',
    'Hangul_RieulKiyeog': '313a',
    'Hangul_RieulMieum': '313b',
    'Hangul_RieulPhieuf': '313f',
    'Hangul_RieulPieub': '313c',
    'Hangul_RieulSios': '313d',
    'Hangul_RieulTieut': '313e',
    'Hangul_RieulYeorinHieuh': '316d',
    'Hangul_Sios': '3145',
    'Hangul_SsangDikeud': '3138',
    'Hangul_SsangJieuj': '3149',
    'Hangul_SsangKiyeog': '3132',
    'Hangul_SsangPieub': '3143',
    'Hangul_SsangSios': '3146',
    'Hangul_SunkyeongeumMieum': '3171',
    'Hangul_SunkyeongeumPhieuf': '3184',
    'Hangul_SunkyeongeumPieub': '3178',
    'Hangul_Tieut': '314c',
    'Hangul_U': '315c',
    'Hangul_WA': '3158',
    'Hangul_WAE': '3159',
    'Hangul_WE': '315e',
    'Hangul_WEO': '315d',
    'Hangul_WI': '315f',
    'Hangul_YA': '3151',
    'Hangul_YAE': '3152',
    'Hangul_YE': '3156',
    'Hangul_YEO': '3155',
    'Hangul_YI': '3162',
    'Hangul_YO': '315b',
    'Hangul_YU': '3160',
    'Hangul_YeorinHieuh': '3186',
    'Hcircumflex': '0124',
    'Hstroke': '0126',
    'I': '0049',
    'Iabovedot': '0130',
    'Iacute': '00cd',
    'Ibelowdot': '1eca',
    'Ibreve': '012c',
    'Icircumflex': '00ce',
    'Idiaeresis': '00cf',
    'Igrave': '00cc',
    'Ihook': '1ec8',
    'Imacron': '012a',
    'Iogonek': '012e',
    'Itilde': '0128',
    'J': '004a',
    'Jcircumflex': '0134',
    'K': '004b',
    'Kcedilla': '0136',
    'Korean_Won': '20a9',
    'L': '004c',
    'Lacute': '0139',
    'Lbelowdot': '1e36',
    'Lcaron': '013d',
    'Lcedilla': '013b',
    'LiraSign': '20a4',
    'Lstroke': '0141',
    'M': '004d',
    'Mabovedot': '1e40',
    'Macedonia_DSE': '0405',
    'Macedonia_GJE': '0403',
    'Macedonia_KJE': '040c',
    'Macedonia_dse': '0455',
    'Macedonia_gje': '0453',
    'Macedonia_kje': '045c',
    'MillSign': '20a5',
    'N': '004e',
    'Nacute': '0143',
    'NairaSign': '20a6',
    'Ncaron': '0147',
    'Ncedilla': '0145',
    'NewSheqelSign': '20aa',
    'Ntilde': '00d1',
    'O': '004f',
    'OE': '0152',
    'Oacute': '00d3',
    'Obarred': '019f',
    'Obelowdot': '1ecc',
    'Ocaron': '01d1',
    'Ocircumflex': '00d4',
    'Ocircumflexacute': '1ed0',
    'Ocircumflexbelowdot': '1ed8',
    'Ocircumflexgrave': '1ed2',
    'Ocircumflexhook': '1ed4',
    'Ocircumflextilde': '1ed6',
    'Odiaeresis': '00d6',
    'Odoubleacute': '0150',
    'Ograve': '00d2',
    'Ohook': '1ece',
    'Ohorn': '01a0',
    'Ohornacute': '1eda',
    'Ohornbelowdot': '1ee2',
    'Ohorngrave': '1edc',
    'Ohornhook': '1ede',
    'Ohorntilde': '1ee0',
    'Omacron': '014c',
    'Ooblique': '00d8',
    'Oslash': '00d8',
    'Otilde': '00d5',
    'P': '0050',
    'Pabovedot': '1e56',
    'PesetaSign': '20a7',
    'Q': '0051',
    'R': '0052',
    'Racute': '0154',
    'Rcaron': '0158',
    'Rcedilla': '0156',
    'RupeeSign': '20a8',
    'S': '0053',
    'SCHWA': '018f',
    'Sabovedot': '1e60',
    'Sacute': '015a',
    'Scaron': '0160',
    'Scedilla': '015e',
    'Schwa': '018f',
    'Scircumflex': '015c',
    'Serbian_DJE': '0402',
    'Serbian_TSHE': '040b',
    'Serbian_dje': '0452',
    'Serbian_tshe': '045b',
    'Sinh_a': '0d85',
    'Sinh_aa': '0d86',
    'Sinh_aa2': '0dcf',
    'Sinh_ae': '0d87',
    'Sinh_ae2': '0dd0',
    'Sinh_aee': '0d88',
    'Sinh_aee2': '0dd1',
    'Sinh_ai': '0d93',
    'Sinh_ai2': '0ddb',
    'Sinh_al': '0dca',
    'Sinh_au': '0d96',
    'Sinh_au2': '0dde',
    'Sinh_ba': '0db6',
    'Sinh_bha': '0db7',
    'Sinh_ca': '0da0',
    'Sinh_cha': '0da1',
    'Sinh_dda': '0da9',
    'Sinh_ddha': '0daa',
    'Sinh_dha': '0daf',
    'Sinh_dhha': '0db0',
    'Sinh_e': '0d91',
    'Sinh_e2': '0dd9',
    'Sinh_ee': '0d92',
    'Sinh_ee2': '0dda',
    'Sinh_fa': '0dc6',
    'Sinh_ga': '0d9c',
    'Sinh_gha': '0d9d',
    'Sinh_h2': '0d83',
    'Sinh_ha': '0dc4',
    'Sinh_i': '0d89',
    'Sinh_i2': '0dd2',
    'Sinh_ii': '0d8a',
    'Sinh_ii2': '0dd3',
    'Sinh_ja': '0da2',
    'Sinh_jha': '0da3',
    'Sinh_jnya': '0da5',
    'Sinh_ka': '0d9a',
    'Sinh_kha': '0d9b',
    'Sinh_la': '0dbd',
    'Sinh_lla': '0dc5',
    'Sinh_lu': '0d8f',
    'Sinh_lu2': '0ddf',
    'Sinh_luu': '0d90',
    'Sinh_luu2': '0df3',
    'Sinh_ma': '0db8',
    'Sinh_mba': '0db9',
    'Sinh_na': '0db1',
    'Sinh_ndda': '0dac',
    'Sinh_ndha': '0db3',
    'Sinh_ng': '0d82',
    'Sinh_ng2': '0d9e',
    'Sinh_nga': '0d9f',
    'Sinh_nja': '0da6',
    'Sinh_nna': '0dab',
    'Sinh_nya': '0da4',
    'Sinh_o': '0d94',
    'Sinh_o2': '0ddc',
    'Sinh_oo': '0d95',
    'Sinh_oo2': '0ddd',
    'Sinh_pa': '0db4',
    'Sinh_pha': '0db5',
    'Sinh_ra': '0dbb',
    'Sinh_ri': '0d8d',
    'Sinh_rii': '0d8e',
    'Sinh_ru2': '0dd8',
    'Sinh_ruu2': '0df2',
    'Sinh_sa': '0dc3',
    'Sinh_sha': '0dc1',
    'Sinh_ssha': '0dc2',
    'Sinh_tha': '0dad',
    'Sinh_thha': '0dae',
    'Sinh_tta': '0da7',
    'Sinh_ttha': '0da8',
    'Sinh_u': '0d8b',
    'Sinh_u2': '0dd4',
    'Sinh_uu': '0d8c',
    'Sinh_uu2': '0dd6',
    'Sinh_va': '0dc0',
    'Sinh_ya': '0dba',
    'T': '0054',
    'THORN': '00de',
    'Tabovedot': '1e6a',
    'Tcaron': '0164',
    'Tcedilla': '0162',
    'Thai_baht': '0e3f',
    'Thai_bobaimai': '0e1a',
    'Thai_chochan': '0e08',
    'Thai_chochang': '0e0a',
    'Thai_choching': '0e09',
    'Thai_chochoe': '0e0c',
    'Thai_dochada': '0e0e',
    'Thai_dodek': '0e14',
    'Thai_fofa': '0e1d',
    'Thai_fofan': '0e1f',
    'Thai_hohip': '0e2b',
    'Thai_honokhuk': '0e2e',
    'Thai_khokhai': '0e02',
    'Thai_khokhon': '0e05',
    'Thai_khokhuat': '0e03',
    'Thai_khokhwai': '0e04',
    'Thai_khorakhang': '0e06',
    'Thai_kokai': '0e01',
    'Thai_lakkhangyao': '0e45',
    'Thai_lekchet': '0e57',
    'Thai_lekha': '0e55',
    'Thai_lekhok': '0e56',
    'Thai_lekkao': '0e59',
    'Thai_leknung': '0e51',
    'Thai_lekpaet': '0e58',
    'Thai_leksam': '0e53',
    'Thai_leksi': '0e54',
    'Thai_leksong': '0e52',
    'Thai_leksun': '0e50',
    'Thai_lochula': '0e2c',
    'Thai_loling': '0e25',
    'Thai_lu': '0e26',
    'Thai_maichattawa': '0e4b',
    'Thai_maiek': '0e48',
    'Thai_maihanakat': '0e31',
    'Thai_maitaikhu': '0e47',
    'Thai_maitho': '0e49',
    'Thai_maitri': '0e4a',
    'Thai_maiyamok': '0e46',
    'Thai_moma': '0e21',
    'Thai_ngongu': '0e07',
    'Thai_nikhahit': '0e4d',
    'Thai_nonen': '0e13',
    'Thai_nonu': '0e19',
    'Thai_oang': '0e2d',
    'Thai_paiyannoi': '0e2f',
    'Thai_phinthu': '0e3a',
    'Thai_phophan': '0e1e',
    'Thai_phophung': '0e1c',
    'Thai_phosamphao': '0e20',
    'Thai_popla': '0e1b',
    'Thai_rorua': '0e23',
    'Thai_ru': '0e24',
    'Thai_saraa': '0e30',
    'Thai_saraaa': '0e32',
    'Thai_saraae': '0e41',
    'Thai_saraaimaimalai': '0e44',
    'Thai_saraaimaimuan': '0e43',
    'Thai_saraam': '0e33',
    'Thai_sarae': '0e40',
    'Thai_sarai': '0e34',
    'Thai_saraii': '0e35',
    'Thai_sarao': '0e42',
    'Thai_sarau': '0e38',
    'Thai_saraue': '0e36',
    'Thai_sarauee': '0e37',
    'Thai_sarauu': '0e39',
    'Thai_sorusi': '0e29',
    'Thai_sosala': '0e28',
    'Thai_soso': '0e0b',
    'Thai_sosua': '0e2a',
    'Thai_thanthakhat': '0e4c',
    'Thai_thonangmontho': '0e11',
    'Thai_thophuthao': '0e12',
    'Thai_thothahan': '0e17',
    'Thai_thothan': '0e10',
    'Thai_thothong': '0e18',
    'Thai_thothung': '0e16',
    'Thai_topatak': '0e0f',
    'Thai_totao': '0e15',
    'Thai_wowaen': '0e27',
    'Thai_yoyak': '0e22',
    'Thai_yoying': '0e0d',
    'Thorn': '00de',
    'Tslash': '0166',
    'U': '0055',
    'Uacute': '00da',
    'Ubelowdot': '1ee4',
    'Ubreve': '016c',
    'Ucircumflex': '00db',
    'Udiaeresis': '00dc',
    'Udoubleacute': '0170',
    'Ugrave': '00d9',
    'Uhook': '1ee6',
    'Uhorn': '01af',
    'Uhornacute': '1ee8',
    'Uhornbelowdot': '1ef0',
    'Uhorngrave': '1eea',
    'Uhornhook': '1eec',
    'Uhorntilde': '1eee',
    'Ukrainian_GHE_WITH_UPTURN': '0490',
    'Ukrainian_I': '0406',
    'Ukrainian_IE': '0404',
    'Ukrainian_YI': '0407',
    'Ukrainian_ghe_with_upturn': '0491',
    'Ukrainian_i': '0456',
    'Ukrainian_ie': '0454',
    'Ukrainian_yi': '0457',
    'Umacron': '016a',
    'Uogonek': '0172',
    'Uring': '016e',
    'Utilde': '0168',
    'V': '0056',
    'W': '0057',
    'Wacute': '1e82',
    'Wcircumflex': '0174',
    'Wdiaeresis': '1e84',
    'Wgrave': '1e80',
    'WonSign': '20a9',
    'X': '0058',
    'Xabovedot': '1e8a',
    'Y': '0059',
    'Yacute': '00dd',
    'Ybelowdot': '1ef4',
    'Ycircumflex': '0176',
    'Ydiaeresis': '0178',
    'Ygrave': '1ef2',
    'Yhook': '1ef6',
    'Ytilde': '1ef8',
    'Z': '005a',
    'Zabovedot': '017b',
    'Zacute': '0179',
    'Zcaron': '017d',
    'Zstroke': '01b5',
    'a': '0061',
    'aacute': '00e1',
    'abelowdot': '1ea1',
    'abovedot': '02d9',
    'abreve': '0103',
    'abreveacute': '1eaf',
    'abrevebelowdot': '1eb7',
    'abrevegrave': '1eb1',
    'abrevehook': '1eb3',
    'abrevetilde': '1eb5',
    'acircumflex': '00e2',
    'acircumflexacute': '1ea5',
    'acircumflexbelowdot': '1ead',
    'acircumflexgrave': '1ea7',
    'acircumflexhook': '1ea9',
    'acircumflextilde': '1eab',
    'acute': '0027',
    'adiaeresis': '00e4',
    'ae': '00e6',
    'agrave': '00e0',
    'ahook': '1ea3',
    'amacron': '0101',
    'ampersand': '0026',
    'aogonek': '0105',
    'apostrophe': '0027',
    'approxeq': '2248',
    'approximate': '223c',
    'aring': '00e5',
    'asciicircum': '005e',
    'asciitilde': '007e',
    'asterisk': '002a',
    'asterix': '002a',
    'at': '0040',
    'atilde': '00e3',
    'b': '0062',
    'babovedot': '1e03',
    'backlash': '005c',
    'backslash': '005c',
    'ballotcross': '2717',
    'bar': '007c',
    'because': '2235',
    'botintegral': '2321',
    'botleftparens': '239d',
    'botleftsqbracket': '23a3',
    'botrightparens': '23a0',
    'botrightsqbracket': '23a6',
    'bott': '2534',
    'braceleft': '007b',
    'braceright': '007d',
    'bracketleft': '005b',
    'bracketright': '005d',
    'braille_dots_1': '2801',
    'braille_dots_12': '2803',
    'braille_dots_123': '2807',
    'braille_dots_1234': '280f',
    'braille_dots_12345': '281f',
    'braille_dots_123456': '283f',
    'braille_dots_1234567': '287f',
    'braille_dots_12345678': '28ff',
    'braille_dots_1234568': '28bf',
    'braille_dots_123457': '285f',
    'braille_dots_1234578': '28df',
    'braille_dots_123458': '289f',
    'braille_dots_12346': '282f',
    'braille_dots_123467': '286f',
    'braille_dots_1234678': '28ef',
    'braille_dots_123468': '28af',
    'braille_dots_12347': '284f',
    'braille_dots_123478': '28cf',
    'braille_dots_12348': '288f',
    'braille_dots_1235': '2817',
    'braille_dots_12356': '2837',
    'braille_dots_123567': '2877',
    'braille_dots_1235678': '28f7',
    'braille_dots_123568': '28b7',
    'braille_dots_12357': '2857',
    'braille_dots_123578': '28d7',
    'braille_dots_12358': '2897',
    'braille_dots_1236': '2827',
    'braille_dots_12367': '2867',
    'braille_dots_123678': '28e7',
    'braille_dots_12368': '28a7',
    'braille_dots_1237': '2847',
    'braille_dots_12378': '28c7',
    'braille_dots_1238': '2887',
    'braille_dots_124': '280b',
    'braille_dots_1245': '281b',
    'braille_dots_12456': '283b',
    'braille_dots_124567': '287b',
    'braille_dots_1245678': '28fb',
    'braille_dots_124568': '28bb',
    'braille_dots_12457': '285b',
    'braille_dots_124578': '28db',
    'braille_dots_12458': '289b',
    'braille_dots_1246': '282b',
    'braille_dots_12467': '286b',
    'braille_dots_124678': '28eb',
    'braille_dots_12468': '28ab',
    'braille_dots_1247': '284b',
    'braille_dots_12478': '28cb',
    'braille_dots_1248': '288b',
    'braille_dots_125': '2813',
    'braille_dots_1256': '2833',
    'braille_dots_12567': '2873',
    'braille_dots_125678': '28f3',
    'braille_dots_12568': '28b3',
    'braille_dots_1257': '2853',
    'braille_dots_12578': '28d3',
    'braille_dots_1258': '2893',
    'braille_dots_126': '2823',
    'braille_dots_1267': '2863',
    'braille_dots_12678': '28e3',
    'braille_dots_1268': '28a3',
    'braille_dots_127': '2843',
    'braille_dots_1278': '28c3',
    'braille_dots_128': '2883',
    'braille_dots_13': '2805',
    'braille_dots_134': '280d',
    'braille_dots_1345': '281d',
    'braille_dots_13456': '283d',
    'braille_dots_134567': '287d',
    'braille_dots_1345678': '28fd',
    'braille_dots_134568': '28bd',
    'braille_dots_13457': '285d',
    'braille_dots_134578': '28dd',
    'braille_dots_13458': '289d',
    'braille_dots_1346': '282d',
    'braille_dots_13467': '286d',
    'braille_dots_134678': '28ed',
    'braille_dots_13468': '28ad',
    'braille_dots_1347': '284d',
    'braille_dots_13478': '28cd',
    'braille_dots_1348': '288d',
    'braille_dots_135': '2815',
    'braille_dots_1356': '2835',
    'braille_dots_13567': '2875',
    'braille_dots_135678': '28f5',
    'braille_dots_13568': '28b5',
    'braille_dots_1357': '2855',
    'braille_dots_13578': '28d5',
    'braille_dots_1358': '2895',
    'braille_dots_136': '2825',
    'braille_dots_1367': '2865',
    'braille_dots_13678': '28e5',
    'braille_dots_1368': '28a5',
    'braille_dots_137': '2845',
    'braille_dots_1378': '28c5',
    'braille_dots_138': '2885',
    'braille_dots_14': '2809',
    'braille_dots_145': '2819',
    'braille_dots_1456': '2839',
    'braille_dots_14567': '2879',
    'braille_dots_145678': '28f9',
    'braille_dots_14568': '28b9',
    'braille_dots_1457': '2859',
    'braille_dots_14578': '28d9',
    'braille_dots_1458': '2899',
    'braille_dots_146': '2829',
    'braille_dots_1467': '2869',
    'braille_dots_14678': '28e9',
    'braille_dots_1468': '28a9',
    'braille_dots_147': '2849',
    'braille_dots_1478': '28c9',
    'braille_dots_148': '2889',
    'braille_dots_15': '2811',
    'braille_dots_156': '2831',
    'braille_dots_1567': '2871',
    'braille_dots_15678': '28f1',
    'braille_dots_1568': '28b1',
    'braille_dots_157': '2851',
    'braille_dots_1578': '28d1',
    'braille_dots_158': '2891',
    'braille_dots_16': '2821',
    'braille_dots_167': '2861',
    'braille_dots_1678': '28e1',
    'braille_dots_168': '28a1',
    'braille_dots_17': '2841',
    'braille_dots_178': '28c1',
    'braille_dots_18': '2881',
    'braille_dots_2': '2802',
    'braille_dots_23': '2806',
    'braille_dots_234': '280e',
    'braille_dots_2345': '281e',
    'braille_dots_23456': '283e',
    'braille_dots_234567': '287e',
    'braille_dots_2345678': '28fe',
    'braille_dots_234568': '28be',
    'braille_dots_23457': '285e',
    'braille_dots_234578': '28de',
    'braille_dots_23458': '289e',
    'braille_dots_2346': '282e',
    'braille_dots_23467': '286e',
    'braille_dots_234678': '28ee',
    'braille_dots_23468': '28ae',
    'braille_dots_2347': '284e',
    'braille_dots_23478': '28ce',
    'braille_dots_2348': '288e',
    'braille_dots_235': '2816',
    'braille_dots_2356': '2836',
    'braille_dots_23567': '2876',
    'braille_dots_235678': '28f6',
    'braille_dots_23568': '28b6',
    'braille_dots_2357': '2856',
    'braille_dots_23578': '28d6',
    'braille_dots_2358': '2896',
    'braille_dots_236': '2826',
    'braille_dots_2367': '2866',
    'braille_dots_23678': '28e6',
    'braille_dots_2368': '28a6',
    'braille_dots_237': '2846',
    'braille_dots_2378': '28c6',
    'braille_dots_238': '2886',
    'braille_dots_24': '280a',
    'braille_dots_245': '281a',
    'braille_dots_2456': '283a',
    'braille_dots_24567': '287a',
    'braille_dots_245678': '28fa',
    'braille_dots_24568': '28ba',
    'braille_dots_2457': '285a',
    'braille_dots_24578': '28da',
    'braille_dots_2458': '289a',
    'braille_dots_246': '282a',
    'braille_dots_2467': '286a',
    'braille_dots_24678': '28ea',
    'braille_dots_2468': '28aa',
    'braille_dots_247': '284a',
    'braille_dots_2478': '28ca',
    'braille_dots_248': '288a',
    'braille_dots_25': '2812',
    'braille_dots_256': '2832',
    'braille_dots_2567': '2872',
    'braille_dots_25678': '28f2',
    'braille_dots_2568': '28b2',
    'braille_dots_257': '2852',
    'braille_dots_2578': '28d2',
    'braille_dots_258': '2892',
    'braille_dots_26': '2822',
    'braille_dots_267': '2862',
    'braille_dots_2678': '28e2',
    'braille_dots_268': '28a2',
    'braille_dots_27': '2842',
    'braille_dots_278': '28c2',
    'braille_dots_28': '2882',
    'braille_dots_3': '2804',
    'braille_dots_34': '280c',
    'braille_dots_345': '281c',
    'braille_dots_3456': '283c',
    'braille_dots_34567': '287c',
    'braille_dots_345678': '28fc',
    'braille_dots_34568': '28bc',
    'braille_dots_3457': '285c',
    'braille_dots_34578': '28dc',
    'braille_dots_3458': '289c',
    'braille_dots_346': '282c',
    'braille_dots_3467': '286c',
    'braille_dots_34678': '28ec',
    'braille_dots_3468': '28ac',
    'braille_dots_347': '284c',
    'braille_dots_3478': '28cc',
    'braille_dots_348': '288c',
    'braille_dots_35': '2814',
    'braille_dots_356': '2834',
    'braille_dots_3567': '2874',
    'braille_dots_35678': '28f4',
    'braille_dots_3568': '28b4',
    'braille_dots_357': '2854',
    'braille_dots_3578': '28d4',
    'braille_dots_358': '2894',
    'braille_dots_36': '2824',
    'braille_dots_367': '2864',
    'braille_dots_3678': '28e4',
    'braille_dots_368': '28a4',
    'braille_dots_37': '2844',
    'braille_dots_378': '28c4',
    'braille_dots_38': '2884',
    'braille_dots_4': '2808',
    'braille_dots_45': '2818',
    'braille_dots_456': '2838',
    'braille_dots_4567': '2878',
    'braille_dots_45678': '28f8',
    'braille_dots_4568': '28b8',
    'braille_dots_457': '2858',
    'braille_dots_4578': '28d8',
    'braille_dots_458': '2898',
    'braille_dots_46': '2828',
    'braille_dots_467': '2868',
    'braille_dots_4678': '28e8',
    'braille_dots_468': '28a8',
    'braille_dots_47': '2848',
    'braille_dots_478': '28c8',
    'braille_dots_48': '2888',
    'braille_dots_5': '2810',
    'braille_dots_56': '2830',
    'braille_dots_567': '2870',
    'braille_dots_5678': '28f0',
    'braille_dots_568': '28b0',
    'braille_dots_57': '2850',
    'braille_dots_578': '28d0',
    'braille_dots_58': '2890',
    'braille_dots_6': '2820',
    'braille_dots_67': '2860',
    'braille_dots_678': '28e0',
    'braille_dots_68': '28a0',
    'braille_dots_7': '2840',
    'braille_dots_78': '28c0',
    'braille_dots_8': '2880',
    'breve': '02d8',
    'brokenbar': '00a6',
    'c': '0063',
    'cabovedot': '010b',
    'cacute': '0107',
    'careof': '2105',
    'caret': '2038',
    'caron': '02c7',
    'ccaron': '010d',
    'ccedilla': '00e7',
    'ccircumflex': '0109',
    'cedilla': '00b8',
    'cent': '00a2',
    'checkerboard': '2592',
    'checkmark': '2713',
    'circle': '25cb',
    'circumflex': '005e',
    'club': '2663',
    'colon': '003a',
    'comma': '002c',
    'containsas': '220B',
    'copyright': '00a9',
    'cr': '240d',
    'crossinglines': '253c',
    'cuberoot': '221b',
    'currency': '00a4',
    'd': '0064',
    'dabovedot': '1e0b',
    'dagger': '2020',
    'dcaron': '010f',
    'degree': '00b0',
    'diaeresis': '00a8',
    'diamond': '2666',
    'digitspace': '2007',
    'dintegral': '222c',
    'division': '00f7',
    'dollar': '0024',
    'doubbaselinedot': '2025',
    'doubleacute': '02dd',
    'doubledagger': '2021',
    'doublelowquotemark': '201e',
    'downarrow': '2193',
    'downcaret': '2228',
    'downshoe': '222a',
    'downstile': '230a',
    'downtack': '22a5',
    'dstroke': '0111',
    'e': '0065',
    'eabovedot': '0117',
    'eacute': '00e9',
    'ebelowdot': '1eb9',
    'ecaron': '011b',
    'ecircumflex': '00ea',
    'ecircumflexacute': '1ebf',
    'ecircumflexbelowdot': '1ec7',
    'ecircumflexgrave': '1ec1',
    'ecircumflexhook': '1ec3',
    'ecircumflextilde': '1ec5',
    'ediaeresis': '00eb',
    'egrave': '00e8',
    'ehook': '1ebb',
    'eightsubscript': '2088',
    'eightsuperior': '2078',
    'elementof': '2208',
    'ellipsis': '2026',
    'em3space': '2004',
    'em4space': '2005',
    'emacron': '0113',
    'emdash': '2014',
    'emfilledcircle': '25cf',
    'emfilledrect': '25ae',
    'emopencircle': '25cb',
    'emopenrectangle': '25af',
    'emptyset': '2205',
    'emspace': '2003',
    'endash': '2013',
    'enfilledcircbullet': '2022',
    'enfilledsqbullet': '25aa',
    'eng': '014b',
    'enopencircbullet': '25e6',
    'enopensquarebullet': '25ab',
    'enspace': '2002',
    'eogonek': '0119',
    'equal': '003d',
    'eth': '00f0',
    'etilde': '1ebd',
    'exclam': '0021',
    'exclamdown': '00a1',
    'ezh': '0292',
    'f': '0066',
    'fabovedot': '1e1f',
    'femalesymbol': '2640',
    'ff': '240c',
    'figdash': '2012',
    'filledlefttribullet': '25c0',
    'filledrectbullet': '25ac',
    'filledrighttribullet': '25b6',
    'filledtribulletdown': '25bc',
    'filledtribulletup': '25b2',
    'fiveeighths': '215d',
    'fivesixths': '215a',
    'fivesubscript': '2085',
    'fivesuperior': '2075',
    'fourfifths': '2158',
    'foursubscript': '2084',
    'foursuperior': '2074',
    'fourthroot': '221c',
    'function': '0192',
    'g': '0067',
    'gabovedot': '0121',
    'gbreve': '011f',
    'gcaron': '01e7',
    'gcedilla': '0123',
    'gcircumflex': '011d',
    'grave': '0060',
    'greater': '003e',
    'greaterthanequal': '2265',
    'guillemotleft': '00ab',
    'guillemotright': '00bb',
    'guilsinglleft': '2039',
    'guilsinglright': '203a',
    'h': '0068',
    'hairspace': '200a',
    'hcircumflex': '0125',
    'heart': '2665',
    'hebrew_aleph': '05d0',
    'hebrew_ayin': '05e2',
    'hebrew_bet': '05d1',
    'hebrew_chet': '05d7',
    'hebrew_dalet': '05d3',
    'hebrew_doublelowline': '2017',
    'hebrew_finalkaph': '05da',
    'hebrew_finalmem': '05dd',
    'hebrew_finalnun': '05df',
    'hebrew_finalpe': '05e3',
    'hebrew_finalzade': '05e5',
    'hebrew_gimel': '05d2',
    'hebrew_he': '05d4',
    'hebrew_kaph': '05db',
    'hebrew_lamed': '05dc',
    'hebrew_mem': '05de',
    'hebrew_nun': '05e0',
    'hebrew_pe': '05e4',
    'hebrew_qoph': '05e7',
    'hebrew_resh': '05e8',
    'hebrew_samech': '05e1',
    'hebrew_shin': '05e9',
    'hebrew_taw': '05ea',
    'hebrew_tet': '05d8',
    'hebrew_waw': '05d5',
    'hebrew_yod': '05d9',
    'hebrew_zade': '05e6',
    'hebrew_zain': '05d6',
    'horizconnector': '2500',
    'horizlinescan1': '23ba',
    'horizlinescan3': '23bb',
    'horizlinescan5': '2500',
    'horizlinescan7': '23bc',
    'horizlinescan9': '23bd',
    'hstroke': '0127',
    'ht': '2409',
    'hyphen': '00ad',
    'i': '0069',
    'iacute': '00ed',
    'ibelowdot': '1ecb',
    'ibreve': '012d',
    'icircumflex': '00ee',
    'identical': '2261',
    'idiaeresis': '00ef',
    'idotless': '0131',
    'ifonlyif': '21d4',
    'igrave': '00ec',
    'ihook': '1ec9',
    'imacron': '012b',
    'implies': '21d2',
    'includedin': '2282',
    'includes': '2283',
    'infinity': '221e',
    'integral': '222b',
    'intersection': '2229',
    'iogonek': '012f',
    'itilde': '0129',
    'j': '006a',
    'jcircumflex': '0135',
    'jot': '2218',
    'k': '006b',
    'kana_A': '30a2',
    'kana_CHI': '30c1',
    'kana_E': '30a8',
    'kana_FU': '30d5',
    'kana_HA': '30cf',
    'kana_HE': '30d8',
    'kana_HI': '30d2',
    'kana_HO': '30db',
    'kana_I': '30a4',
    'kana_KA': '30ab',
    'kana_KE': '30b1',
    'kana_KI': '30ad',
    'kana_KO': '30b3',
    'kana_KU': '30af',
    'kana_MA': '30de',
    'kana_ME': '30e1',
    'kana_MI': '30df',
    'kana_MO': '30e2',
    'kana_MU': '30e0',
    'kana_N': '30f3',
    'kana_NA': '30ca',
    'kana_NE': '30cd',
    'kana_NI': '30cb',
    'kana_NO': '30ce',
    'kana_NU': '30cc',
    'kana_O': '30aa',
    'kana_RA': '30e9',
    'kana_RE': '30ec',
    'kana_RI': '30ea',
    'kana_RO': '30ed',
    'kana_RU': '30eb',
    'kana_SA': '30b5',
    'kana_SE': '30bb',
    'kana_SHI': '30b7',
    'kana_SO': '30bd',
    'kana_SU': '30b9',
    'kana_TA': '30bf',
    'kana_TE': '30c6',
    'kana_TO': '30c8',
    'kana_TSU': '30c4',
    'kana_U': '30a6',
    'kana_WA': '30ef',
    'kana_WO': '30f2',
    'kana_YA': '30e4',
    'kana_YO': '30e8',
    'kana_YU': '30e6',
    'kana_a': '30a1',
    'kana_closingbracket': '300d',
    'kana_comma': '3001',
    'kana_conjunctive': '30fb',
    'kana_e': '30a7',
    'kana_fullstop': '3002',
    'kana_i': '30a3',
    'kana_middledot': '30fb',
    'kana_o': '30a9',
    'kana_openingbracket': '300c',
    'kana_tsu': '30c3',
    'kana_u': '30a5',
    'kana_ya': '30e3',
    'kana_yo': '30e7',
    'kana_yu': '30e5',
    'kcedilla': '0137',
    'kra': '0138',
    'l': '006c',
    'lacute': '013a',
    'latincross': '271d',
    'lbelowdot': '1e37',
    'lcaron': '013e',
    'lcedilla': '013c',
    'leftanglebracket': '2329',
    'leftarrow': '2190',
    'leftdoublequotemark': '201c',
    'leftmiddlecurlybrace': '23a8',
    'leftopentriangle': '25c1',
    'leftpointer': '261c',
    'leftradical': '23b7',
    'leftshoe': '2282',
    'leftsinglequotemark': '2018',
    'leftt': '251c',
    'lefttack': '22a2',
    'less': '003c',
    'lessthanequal': '2264',
    'lf': '240a',
    'logicaland': '2227',
    'logicalor': '2228',
    'lowleftcorner': '2514',
    'lowrightcorner': '2518',
    'lstroke': '0142',
    'm': '006d',
    'mabovedot': '1e41',
    'macron': '00af',
    'malesymbol': '2642',
    'maltesecross': '2720',
    'masculine': '00ba',
    'minus': '002d',
    'minutes': '2032',
    'mu': '00b5',
    'multiply': '00d7',
    'musicalflat': '266d',
    'musicalsharp': '266f',
    'n': '006e',
    'nabla': '2207',
    'nacute': '0144',
    'ncaron': '0148',
    'ncedilla': '0146',
    'ninesubscript': '2089',
    'ninesuperior': '2079',
    'nl': '2424',
    'nobreakspace': '00a0',
    'notapproxeq': '2247',
    'notelementof': '2209',
    'notequal': '2260',
    'notidentical': '2262',
    'notsign': '00ac',
    'ntilde': '00f1',
    'numbersign': '0023',
    'numerosign': '2116',
    'o': '006f',
    'oacute': '00f3',
    'obarred': '0275',
    'obelowdot': '1ecd',
    'ocaron': '01d2',
    'ocircumflex': '00f4',
    'ocircumflexacute': '1ed1',
    'ocircumflexbelowdot': '1ed9',
    'ocircumflexgrave': '1ed3',
    'ocircumflexhook': '1ed5',
    'ocircumflextilde': '1ed7',
    'odiaeresis': '00f6',
    'odoubleacute': '0151',
    'oe': '0153',
    'ogonek': '02db',
    'ograve': '00f2',
    'ohook': '1ecf',
    'ohorn': '01a1',
    'ohornacute': '1edb',
    'ohornbelowdot': '1ee3',
    'ohorngrave': '1edd',
    'ohornhook': '1edf',
    'ohorntilde': '1ee1',
    'omacron': '014d',
    'oneeighth': '215b',
    'onefifth': '2155',
    'onehalf': '00bd',
    'onequarter': '00bc',
    'onesixth': '2159',
    'onesubscript': '2081',
    'onesuperior': '00b9',
    'onethird': '2153',
    'ooblique': '00f8',
    'openrectbullet': '25ad',
    'openstar': '2606',
    'opentribulletdown': '25bd',
    'opentribulletup': '25b3',
    'ordfeminine': '00aa',
    'oslash': '00f8',
    'otilde': '00f5',
    'overbar': '00af',
    'overline': '203e',
    'p': '0070',
    'pabovedot': '1e57',
    'paragraph': '00b6',
    'parenlef': '0028',
    'parenleft': '0028',
    'parenright': '0029',
    'partdifferential': '2202',
    'partialderivative': '2202',
    'percent': '0025',
    'period': '002e',
    'periodcentered': '00b7',
    'permille': '2030',
    'phonographcopyright': '2117',
    'pipe': '007c',
    'plus': '002b',
    'plusminus': '00b1',
    'prescription': '211e',
    'prolongedsound': '30fc',
    'punctspace': '2008',
    'q': '0071',
    'quad': '2395',
    'question': '003f',
    'questiondown': '00bf',
    'quotedbl': '0022',
    'quoteleft': '0060',
    'quoteright': '0027',
    'r': '0072',
    'racute': '0155',
    'radical': '221a',
    'rcaron': '0159',
    'rcedilla': '0157',
    'registered': '00ae',
    'rightanglebracket': '232a',
    'rightarrow': '2192',
    'rightdoublequotemark': '201d',
    'rightmiddlecurlybrace': '23ac',
    'rightopentriangle': '25b7',
    'rightpointer': '261e',
    'rightshoe': '2283',
    'rightsinglequotemark': '2019',
    'rightt': '2524',
    'righttack': '22a3',
    's': '0073',
    'sabovedot': '1e61',
    'sacute': '015b',
    'scaron': '0161',
    'scedilla': '015f',
    'schwa': '0259',
    'scircumflex': '015d',
    'seconds': '2033',
    'section': '00a7',
    'semicolon': '003b',
    'semivoicedsound': '309c',
    'seveneighths': '215e',
    'sevensubscript': '2087',
    'sevensuperior': '2077',
    'signaturemark': '2613',
    'similarequal': '2243',
    'singlelowquotemark': '201a',
    'sixsubscript': '2086',
    'sixsuperior': '2076',
    'slash': '002f',
    'soliddiamond': '25c6',
    'space': '0020',
    'squareroot': '221a',
    'ssharp': '00df',
    'sterling': '00a3',
    'stricteq': '2263',
    't': '0074',
    'tabovedot': '1e6b',
    'tcaron': '0165',
    'tcedilla': '0163',
    'telephone': '260e',
    'telephonerecorder': '2315',
    'therefore': '2234',
    'thinspace': '2009',
    'thorn': '00fe',
    'threeeighths': '215c',
    'threefifths': '2157',
    'threequarters': '00be',
    'threesubscript': '2083',
    'threesuperior': '00b3',
    'tintegral': '222d',
    'topintegral': '2320',
    'topleftparens': '239b',
    'topleftradical': '250c',
    'topleftsqbracket': '23a1',
    'toprightparens': '239e',
    'toprightsqbracket': '23a4',
    'topt': '252c',
    'trademark': '2122',
    'tslash': '0167',
    'twofifths': '2156',
    'twosubscript': '2082',
    'twosuperior': '00b2',
    'twothirds': '2154',
    'u': '0075',
    'uacute': '00fa',
    'ubelowdot': '1ee5',
    'ubreve': '016d',
    'ucircumflex': '00fb',
    'udiaeresis': '00fc',
    'udoubleacute': '0171',
    'ugrave': '00f9',
    'uhook': '1ee7',
    'uhorn': '01b0',
    'uhornacute': '1ee9',
    'uhornbelowdot': '1ef1',
    'uhorngrave': '1eeb',
    'uhornhook': '1eed',
    'uhorntilde': '1eef',
    'umacron': '016b',
    'underscore': '005f',
    'union': '222a',
    'uogonek': '0173',
    'uparrow': '2191',
    'upcaret': '2227',
    'upleftcorner': '250c',
    'uprightcorner': '2510',
    'upshoe': '2229',
    'upstile': '2308',
    'uptack': '22a4',
    'uring': '016f',
    'utilde': '0169',
    'v': '0076',
    'variation': '221d',
    'vertbar': '2502',
    'vertconnector': '2502',
    'voicedsound': '309b',
    'vt': '240b',
    'w': '0077',
    'wacute': '1e83',
    'wcircumflex': '0175',
    'wdiaeresis': '1e85',
    'wgrave': '1e81',
    'x': '0078',
    'xabovedot': '1e8b',
    'y': '0079',
    'yacute': '00fd',
    'ybelowdot': '1ef5',
    'ycircumflex': '0177',
    'ydiaeresis': '00ff',
    'yen': '00a5',
    'ygrave': '1ef3',
    'yhook': '1ef7',
    'ytilde': '1ef9',
    'z': '007a',
    'zabovedot': '017c',
    'zacute': '017a',
    'zcaron': '017e',
    'zerosubscript': '2080',
    'zerosuperior': '2070',
    'zstroke': '01b6',
}

# Added to XKBSYM_TABLE only in -freebsd mode (merged over the base table).
XKBSYM_TABLE_FREEBSD_ADD = {
    '0x1000': 'nop',
    '0x13a4': 'nop',
    '0xfe11': 'nop',
    'Alt_L': 'lalt',
    'Alt_R': 'ralt',
    'BackSpace': 'bs',
    'Begin': 'fkey54',
    'Break': 'nop',
    'Cancel': 'nop',
    'Caps_Lock': 'clock',
    'Clear': 'nop',
    'Codeinput': 'nop',
    'Control_L': 'lctrl',
    'Control_R': 'rctrl',
    'Delete': 'fkey61',
    'Down': 'fkey58',
    'Eisu_toggle': 'nop',
    'End': 'fkey57',
    'Escape': 'esc',
    'Execute': 'nop',
    'F1': 'fkey01',
    'F10': 'fkey10',
    'F11': 'fkey11',
    'F12': 'fkey12',
    'F13': 'fkey13',
    'F14': 'fkey14',
    'F15': 'fkey15',
    'F16': 'fkey16',
    'F17': 'fkey17',
    'F18': 'fkey18',
    'F19': 'fkey19',
    'F2': 'fkey02',
    'F20': 'fkey20',
    'F21': 'fkey21',
    'F22': 'fkey22',
    'F23': 'fkey23',
    'F24': 'fkey24',
    'F25': 'fkey25',
    'F26': 'fkey26',
    'F27': 'fkey27',
    'F28': 'fkey28',
    'F29': 'fkey29',
    'F3': 'fkey03',
    'F30': 'fkey30',
    'F31': 'fkey31',
    'F32': 'fkey32',
    'F33': 'fkey33',
    'F34': 'fkey34',
    'F35': 'fkey35',
    'F4': 'fkey04',
    'F5': 'fkey05',
    'F6': 'fkey06',
    'F7': 'fkey07',
    'F8': 'fkey08',
    'F9': 'fkey09',
    'Find': 'fkey49',
    'Hangul': 'nop',
    'Hangul_Hanja': 'nop',
    'Help': 'slock',
    'Henkan': 'nop',
    'Hiragana': 'nop',
    'Hiragana_Katakana': 'nop',
    'Home': 'fkey49',
    'Hyper_L': 'meta',
    'Hyper_R': 'meta',
    'ISO_First_Group': 'alock',
    'ISO_First_Group_Lock': 'alock',
    'ISO_Group_Latch': 'ashift',
    'ISO_Group_Lock': 'alock',
    'ISO_Group_Shift': 'ashift',
    'ISO_Last_Group': 'alock',
    'ISO_Last_Group_Lock': 'alock',
    'ISO_Left_Tab': 'ht',
    'ISO_Level2_Latch': 'lshift',
    'ISO_Level3_Latch': 'alt',
    'ISO_Level3_Lock': 'alta',
    'ISO_Level3_Shift': 'alt',
    'ISO_Level5_Latch': 'alt',
    'ISO_Level5_Lock': 'alta',
    'ISO_Level5_Shift': 'alt',
    'ISO_Lock': 'clock',
    'ISO_Next_Group': 'alock',
    'ISO_Next_Group_Lock': 'alock',
    'ISO_Prev_Group': 'alock',
    'ISO_Prev_Group_Lock': 'alock',
    'Insert': 'fkey60',
    'KP_0': "'0'",
    'KP_1': "'1'",
    'KP_2': "'2'",
    'KP_3': "'3'",
    'KP_4': "'4'",
    'KP_5': "'5'",
    'KP_6': "'6'",
    'KP_7': "'7'",
    'KP_8': "'8'",
    'KP_9': "'9'",
    'KP_Add': 'fkey56',
    'KP_Begin': 'fkey54',
    'KP_Decimal': "'.'",
    'KP_Delete': 'del',
    'KP_Divide': "'/'",
    'KP_Down': 'fkey58',
    'KP_End': 'fkey57',
    'KP_Enter': 'cr',
    'KP_Equal': "'='",
    'KP_F1': 'fkey01',
    'KP_F2': 'fkey02',
    'KP_F3': 'fkey03',
    'KP_F4': 'fkey04',
    'KP_Home': 'fkey49',
    'KP_Insert': 'fkey60',
    'KP_Left': 'fkey53',
    'KP_Multiply': "'*'",
    'KP_Next': 'fkey59',
    'KP_Page_Down': 'fkey59',
    'KP_Page_Up': 'fkey51',
    'KP_Prior': 'fkey51',
    'KP_Right': 'fkey55',
    'KP_Separator': "','",
    'KP_Seprator': "','",
    'KP_Space': 'sp',
    'KP_Subtract': 'fkey52',
    'KP_Tab': 'ht',
    'KP_Up': 'fkey50',
    'Kanji': 'nop',
    'Katakana': 'nop',
    'L1': 'fkey11',
    'L10': 'fkey20',
    'L2': 'fkey12',
    'L3': 'fkey13',
    'L4': 'fkey14',
    'L5': 'fkey15',
    'L6': 'fkey16',
    'L7': 'fkey17',
    'L8': 'fkey18',
    'L9': 'fkey19',
    'Left': 'fkey53',
    'Linefeed': 'nl',
    'Menu': 'fkey64',
    'Meta_L': 'meta',
    'Meta_R': 'meta',
    'Mode_switch': 'ashift',
    'Muhenkan': 'nop',
    'Multi_key': 'nop',
    'MultipleCandidate': 'nop',
    'Next': 'fkey59',
    'NoAction': 'NoSymbol',
    'NoSymbol': 'NoSymbol',
    'Nosymbol': 'NoSymbol',
    'Num_Lock': 'nlock',
    'Page_Down': 'fkey59',
    'Page_Up': 'fkey51',
    'Pause': 'saver',
    'Pointer_EnableKeys': 'nop',
    'PreviousCandidate': 'nop',
    'Print': 'nscr',
    'Prior': 'fkey51',
    'R1': 'fkey21',
    'R10': 'fkey30',
    'R11': 'fkey31',
    'R12': 'fkey32',
    'R13': 'fkey33',
    'R14': 'fkey34',
    'R15': 'fkey35',
    'R2': 'fkey22',
    'R3': 'fkey23',
    'R4': 'fkey24',
    'R5': 'fkey25',
    'R6': 'fkey26',
    'R7': 'fkey27',
    'R8': 'fkey28',
    'R9': 'fkey29',
    'Redo': 'nop',
    'Return': 'cr',
    'Right': 'fkey55',
    'Scroll_Lock': 'slock',
    'Select': 'fkey57',
    'Shift_L': 'lshift',
    'Shift_Lock': 'clock',
    'Shift_R': 'rshift',
    'SingleCandidate': 'nop',
    'SunAgain': 'nop',
    'SunAudioLowerVolume': 'nop',
    'SunAudioMute': 'nop',
    'SunAudioRaiseVolume': 'nop',
    'SunCopy': 'nop',
    'SunCut': 'nop',
    'SunF36': 'nop',
    'SunF37': 'nop',
    'SunFA_Acute': 'dacu',
    'SunFA_Cedilla': 'dced',
    'SunFA_Circum': 'dcir',
    'SunFA_Diaeresis': 'ddia',
    'SunFA_Grave': 'dgra_grave',
    'SunFA_Tilde': 'dtil',
    'SunFind': 'nop',
    'SunFront': 'nop',
    'SunOpen': 'nop',
    'SunPaste': 'nop',
    'SunPowerSwitch': 'nop',
    'SunPowerSwitchShift': 'nop',
    'SunProps': 'nop',
    'SunStop': 'nop',
    'SunSys_Req': 'nop',
    'SunUndo': 'nop',
    'SunVideoDegauss': 'nop',
    'SunVideoLowerBrightness': 'nop',
    'SunVideoRaiseBrightness': 'nop',
    'Super_L': 'fkey62',
    'Super_R': 'fkey63',
    'Sys_Req': 'nop',
    'Tab': 'ht',
    'Terminate_Server': 'nop',
    'Undo': 'nop',
    'Up': 'fkey50',
    'VoidSymbol': 'nop',
    'XF86AudioForward': 'nop',
    'XF86AudioLowerVolume': 'nop',
    'XF86AudioMedia': 'nop',
    'XF86AudioMute': 'nop',
    'XF86AudioNext': 'nop',
    'XF86AudioPause': 'nop',
    'XF86AudioPlay': 'nop',
    'XF86AudioPrev': 'nop',
    'XF86AudioRaiseVolume': 'nop',
    'XF86AudioRecord': 'nop',
    'XF86AudioRewind': 'nop',
    'XF86AudioStop': 'nop',
    'XF86Back': 'nop',
    'XF86Battery': 'nop',
    'XF86Bluetooth': 'nop',
    'XF86Calculator': 'nop',
    'XF86Close': 'nop',
    'XF86Copy': 'nop',
    'XF86Cut': 'nop',
    'XF86DOS': 'nop',
    'XF86Display': 'nop',
    'XF86Documents': 'nop',
    'XF86Eject': 'nop',
    'XF86Explorer': 'nop',
    'XF86Favorites': 'nop',
    'XF86Finance': 'nop',
    'XF86Forward': 'nop',
    'XF86HomePage': 'nop',
    'XF86KbdBrightnessDown': 'nop',
    'XF86KbdBrightnessUp': 'nop',
    'XF86KbdLightOnOff': 'nop',
    'XF86Launch1': 'nop',
    'XF86Launch2': 'nop',
    'XF86Launch3': 'nop',
    'XF86Launch4': 'nop',
    'XF86Mail': 'nop',
    'XF86MailForward': 'nop',
    'XF86MenuKB': 'nop',
    'XF86MonBrightnessDown': 'nop',
    'XF86MonBrightnessUp': 'nop',
    'XF86MyComputer': 'nop',
    'XF86New': 'nop',
    'XF86Paste': 'nop',
    'XF86Phone': 'nop',
    'XF86PowerOff': 'nop',
    'XF86Reload': 'nop',
    'XF86Reply': 'nop',
    'XF86RotateWindows': 'nop',
    'XF86Save': 'nop',
    'XF86ScreenSaver': 'nop',
    'XF86ScrollDown': 'nop',
    'XF86ScrollUp': 'nop',
    'XF86Search': 'nop',
    'XF86Send': 'nop',
    'XF86Shop': 'nop',
    'XF86Sleep': 'nop',
    'XF86Suspend': 'nop',
    'XF86Tools': 'nop',
    'XF86TouchpadToggle': 'nop',
    'XF86WLAN': 'nop',
    'XF86WWW': 'nop',
    'XF86WakeUp': 'nop',
    'XF86WebCam': 'nop',
    'XF86Xfer': 'nop',
    'XF86_ClearGrab': 'nop',
    'XF86_Next_VMode': 'nop',
    'XF86_Prev_VMode': 'nop',
    'XF86_Switch_VT_1': 'scr01',
    'XF86_Switch_VT_10': 'scr10',
    'XF86_Switch_VT_11': 'scr11',
    'XF86_Switch_VT_12': 'scr12',
    'XF86_Switch_VT_2': 'scr02',
    'XF86_Switch_VT_3': 'scr03',
    'XF86_Switch_VT_4': 'scr04',
    'XF86_Switch_VT_5': 'scr05',
    'XF86_Switch_VT_6': 'scr06',
    'XF86_Switch_VT_7': 'scr07',
    'XF86_Switch_VT_8': 'scr08',
    'XF86_Switch_VT_9': 'scr09',
    'XF86_Ungrab': 'nop',
    'Zenkaku_Hankaku': 'nop',
    'any': 'NoSymbol',
    'braille_blank': '2800',
    'braille_dot_1': 'nop',
    'braille_dot_10': 'nop',
    'braille_dot_2': 'nop',
    'braille_dot_3': 'nop',
    'braille_dot_4': 'nop',
    'braille_dot_5': 'nop',
    'braille_dot_6': 'nop',
    'braille_dot_7': 'nop',
    'braille_dot_8': 'nop',
    'braille_dot_9': 'nop',
    'dead_V': 'dcar',
    'dead_abovedot': 'ddot',
    'dead_abovering': 'drin',
    'dead_acute': 'dacu',
    'dead_belowcomma': 'nop',
    'dead_belowdot': '0323',
    'dead_breve': 'dbre',
    'dead_caron': 'dcar',
    'dead_cedilla': 'dced',
    'dead_circumflex': 'dcir',
    'dead_currency': 'nop',
    'dead_dasia': 'nop',
    'dead_diaeresis': 'ddia',
    'dead_doubleacute': 'ddac',
    'dead_doublegrave': 'nop',
    'dead_grave': 'dgra',
    'dead_greek': 'fe8c',
    'dead_hook': 'dsla',
    'dead_horn': '031b',
    'dead_invertedbreve': 'nop',
    'dead_iota': '03b9',
    'dead_macron': 'dmac',
    'dead_ogonek': 'dogo',
    'dead_psili': 'nop',
    'dead_stroke': 'nop',
    'dead_tilde': 'dtil',
    'guj_llla': 'nop',
    'guj_nnna': 'nop',
    'guj_rra': 'nop',
    'gur_v_r': 'nop',
    'gur_v_r_s': 'nop',
    'gur_visarga': 'nop',
    'leftcaret': 'nop',
    'noSymbol': 'NoSymbol',
    'nosymbol': 'NoSymbol',
    'script_switch': 'nop',
    'voidsymbol': 'nop',
}

KERNEL_MODIFIERS = {
    'Alt': 8,
    'AltGr': 2,
    'AltGr_Lock': 2,
    'Alt_Lock': 8,
    'Control': 4,
    'Control_Lock': 4,
    'CtrlL': 64,
    'CtrlL_Lock': 64,
    'CtrlR': 128,
    'CtrlR_Lock': 128,
    'Shift': 1,
    'ShiftL': 16,
    'ShiftL_Lock': 16,
    'ShiftR': 32,
    'ShiftR_Lock': 32,
    'Shift_Lock': 1,
    'alock': 16,
    'alt': 2,
    'alta': 2,
    'ashift': 16,
    'ctrl': 4,
    'ctrla': 4,
    'lalt': 2,
    'lalta': 2,
    'lctrl': 4,
    'lctrla': 4,
    'lshift': 1,
    'lshifta': 1,
    'ralt': 2,
    'ralta': 2,
    'rctrl': 4,
    'rctrla': 4,
    'rshift': 1,
    'rshifta': 1,
    'shifta': 1,
}

MODIFIER_COMBINATIONS = [
    'plain',
    'shift',
    'altgr',
    'altgr shift',
    'control',
    'control shift',
    'control altgr',
    'control altgr shift',
    'alt',
    'alt shift',
    'alt altgr',
    'alt altgr shift',
    'alt control',
    'alt control shift',
    'alt control altgr',
    'alt control altgr shift',
    'shiftl',
    'shiftl shift',
    'shiftl altgr',
    'shiftl altgr shift',
    'shiftl control',
    'shiftl control shift',
    'shiftl control altgr',
    'shiftl control altgr shift',
    'shiftl alt',
    'shiftl alt shift',
    'shiftl alt altgr',
    'shiftl alt altgr shift',
    'shiftl alt control',
    'shiftl alt control shift',
    'shiftl alt control altgr',
    'shiftl alt control altgr shift',
    'shiftr',
    'shiftr shift',
    'shiftr altgr',
    'shiftr altgr shift',
    'shiftr control',
    'shiftr control shift',
    'shiftr control altgr',
    'shiftr control altgr shift',
    'shiftr alt',
    'shiftr alt shift',
    'shiftr alt altgr',
    'shiftr alt altgr shift',
    'shiftr alt control',
    'shiftr alt control shift',
    'shiftr alt control altgr',
    'shiftr alt control altgr shift',
    'shiftr shiftl',
    'shiftr shiftl shift',
    'shiftr shiftl altgr',
    'shiftr shiftl altgr shift',
    'shiftr shiftl control',
    'shiftr shiftl control shift',
    'shiftr shiftl control altgr',
    'shiftr shiftl control altgr shift',
    'shiftr shiftl alt',
    'shiftr shiftl alt shift',
    'shiftr shiftl alt altgr',
    'shiftr shiftl alt altgr shift',
    'shiftr shiftl alt control',
    'shiftr shiftl alt control shift',
    'shiftr shiftl alt control altgr',
    'shiftr shiftl alt control altgr shift',
    'ctrll',
    'ctrll shift',
    'ctrll altgr',
    'ctrll altgr shift',
    'ctrll control',
    'ctrll control shift',
    'ctrll control altgr',
    'ctrll control altgr shift',
    'ctrll alt',
    'ctrll alt shift',
    'ctrll alt altgr',
    'ctrll alt altgr shift',
    'ctrll alt control',
    'ctrll alt control shift',
    'ctrll alt control altgr',
    'ctrll alt control altgr shift',
    'ctrll shiftl',
    'ctrll shiftl shift',
    'ctrll shiftl altgr',
    'ctrll shiftl altgr shift',
    'ctrll shiftl control',
    'ctrll shiftl control shift',
    'ctrll shiftl control altgr',
    'ctrll shiftl control altgr shift',
    'ctrll shiftl alt',
    'ctrll shiftl alt shift',
    'ctrll shiftl alt altgr',
    'ctrll shiftl alt altgr shift',
    'ctrll shiftl alt control',
    'ctrll shiftl alt control shift',
    'ctrll shiftl alt control altgr',
    'ctrll shiftl alt control altgr shift',
    'ctrll shiftr',
    'ctrll shiftr shift',
    'ctrll shiftr altgr',
    'ctrll shiftr altgr shift',
    'ctrll shiftr control',
    'ctrll shiftr control shift',
    'ctrll shiftr control altgr',
    'ctrll shiftr control altgr shift',
    'ctrll shiftr alt',
    'ctrll shiftr alt shift',
    'ctrll shiftr alt altgr',
    'ctrll shiftr alt altgr shift',
    'ctrll shiftr alt control',
    'ctrll shiftr alt control shift',
    'ctrll shiftr alt control altgr',
    'ctrll shiftr alt control altgr shift',
    'ctrll shiftr shiftl',
    'ctrll shiftr shiftl shift',
    'ctrll shiftr shiftl altgr',
    'ctrll shiftr shiftl altgr shift',
    'ctrll shiftr shiftl control',
    'ctrll shiftr shiftl control shift',
    'ctrll shiftr shiftl control altgr',
    'ctrll shiftr shiftl control altgr shift',
    'ctrll shiftr shiftl alt',
    'ctrll shiftr shiftl alt shift',
    'ctrll shiftr shiftl alt altgr',
    'ctrll shiftr shiftl alt altgr shift',
    'ctrll shiftr shiftl alt control',
    'ctrll shiftr shiftl alt control shift',
    'ctrll shiftr shiftl alt control altgr',
    'ctrll shiftr shiftl alt control altgr shift',
]

# Control-symbol name -> code, FreeBSD variant.
CONTROLSYMS_HASH_FREEBSD = {
    'ack': 6,
    'bel': 7,
    'bs': 8,
    'can': 24,
    'cr': 13,
    'dc1': 17,
    'dc2': 18,
    'dc3': 19,
    'dc4': 20,
    'del': 127,
    'dle': 16,
    'em': 25,
    'enq': 5,
    'eot': 4,
    'esc': 27,
    'etb': 23,
    'etx': 3,
    'ff': 12,
    'fs': 28,
    'gs': 29,
    'ht': 9,
    'nak': 21,
    'nl': 10,
    'nul': 0,
    'rs': 30,
    'si': 15,
    'so': 14,
    'soh': 1,
    'stx': 2,
    'sub': 26,
    'syn': 22,
    'us': 31,
    'vt': 11,
}

# Control-symbol name -> code, non-FreeBSD (Linux) variant.
CONTROLSYMS_HASH_LINUX = {
    'BackSpace': 8,
    'Control_a': 1,
    'Control_asciicircum': 30,
    'Control_b': 2,
    'Control_backslash': 28,
    'Control_bracketright': 29,
    'Control_c': 3,
    'Control_d': 4,
    'Control_e': 5,
    'Control_f': 6,
    'Control_g': 7,
    'Control_k': 11,
    'Control_l': 12,
    'Control_n': 14,
    'Control_o': 15,
    'Control_p': 16,
    'Control_q': 17,
    'Control_r': 18,
    'Control_s': 19,
    'Control_t': 20,
    'Control_u': 21,
    'Control_underscore': 31,
    'Control_v': 22,
    'Control_w': 23,
    'Control_x': 24,
    'Control_y': 25,
    'Control_z': 26,
    'Delete': 127,
    'Escape': 27,
    'Linefeed': 10,
    'Return': 13,
    'Tab': 9,
    'nul': 0,
}

# Meta-symbol source map: single char -> its X keysym name (keys are real chars).
METASYMS_HASH = {
    '\x08': 'BackSpace',
    '\t': 'Tab',
    '\n': 'Linefeed',
    '\r': 'Control_m',
    '\x1b': 'Escape',
    '\x1c': 'Control_backslash',
    ' ': 'space',
    '!': 'exclam',
    '"': 'quotedbl',
    '#': 'numbersign',
    '$': 'dollar',
    '%': 'percent',
    '&': 'ampersand',
    "'": 'apostrophe',
    '(': 'parenleft',
    ')': 'parenright',
    '*': 'asterisk',
    '+': 'plus',
    ',': 'comma',
    '-': 'minus',
    '.': 'period',
    '/': 'slash',
    '0': 'zero',
    '1': 'one',
    '2': 'two',
    '3': 'three',
    '4': 'four',
    '5': 'five',
    '6': 'six',
    '7': 'seven',
    '8': 'eight',
    '9': 'nine',
    ':': 'colon',
    ';': 'semicolon',
    '<': 'less',
    '=': 'equal',
    '>': 'greater',
    '?': 'question',
    '@': 'at',
    '[': 'bracketleft',
    '\\': 'backslash',
    ']': 'bracketright',
    '^': 'asciicircum',
    '_': 'underscore',
    '`': 'grave',
    '{': 'braceleft',
    '|': 'bar',
    '}': 'braceright',
    '~': 'asciitilde',
    '\x7f': 'Delete',
}

# X keycode name (as a string of digits) -> AT scancode.
AT_SCANCODES = {
    '10': 2,
    '100': 105,
    '102': 106,
    '103': 107,
    '104': 108,
    '105': 109,
    '106': 110,
    '107': 111,
    '108': 96,
    '109': 97,
    '11': 3,
    '110': 119,
    '111': 99,
    '112': 98,
    '113': 100,
    '114': 101,
    '115': 125,
    '116': 126,
    '117': 127,
    '118': -1,
    '119': -1,
    '12': 4,
    '120': -1,
    '123': -1,
    '124': -1,
    '125': -1,
    '126': -1,
    '127': -1,
    '128': -1,
    '129': -1,
    '13': 5,
    '131': -1,
    '133': 124,
    '134': 121,
    '14': 6,
    '144': -1,
    '15': 7,
    '156': -1,
    '16': 8,
    '17': 9,
    '18': 10,
    '19': 11,
    '20': 12,
    '208': -1,
    '209': -1,
    '21': 13,
    '210': -1,
    '211': 89,
    '214': -1,
    '215': -1,
    '216': -1,
    '217': -1,
    '22': 14,
    '23': 15,
    '24': 16,
    '25': 17,
    '26': 18,
    '27': 19,
    '28': 20,
    '29': 21,
    '30': 22,
    '31': 23,
    '32': 24,
    '33': 25,
    '34': 26,
    '35': 27,
    '36': 28,
    '37': 29,
    '38': 30,
    '39': 31,
    '40': 32,
    '41': 33,
    '42': 34,
    '43': 35,
    '44': 36,
    '45': 37,
    '46': 38,
    '47': 39,
    '48': 40,
    '49': 41,
    '50': 42,
    '51': 43,
    '52': 44,
    '53': 45,
    '54': 46,
    '55': 47,
    '56': 48,
    '57': 49,
    '58': 50,
    '59': 51,
    '60': 52,
    '61': 53,
    '62': 54,
    '63': 55,
    '64': 56,
    '65': 57,
    '66': 58,
    '67': 59,
    '68': 60,
    '69': 61,
    '70': 62,
    '71': 63,
    '72': 64,
    '73': 65,
    '74': 66,
    '75': 67,
    '76': 68,
    '77': 69,
    '78': 70,
    '79': 71,
    '80': 72,
    '81': 73,
    '82': 74,
    '83': 75,
    '84': 76,
    '85': 77,
    '86': 78,
    '87': 79,
    '88': 80,
    '89': 81,
    '9': 1,
    '90': 82,
    '91': 83,
    '92': 84,
    '93': -1,
    '94': 86,
    '95': 87,
    '96': 88,
    '97': 102,
    '98': 103,
    '99': 104,
}

FREEBSD_SCANCODES = {
    '10': 2,
    '100': 97,
    '102': 98,
    '103': 99,
    '104': 100,
    '105': 101,
    '106': 102,
    '107': 103,
    '108': 89,
    '109': 90,
    '11': 3,
    '110': 104,
    '111': 92,
    '112': 91,
    '113': 93,
    '114': 108,
    '115': 105,
    '116': 106,
    '117': 107,
    '118': -1,
    '119': -1,
    '12': 4,
    '120': -1,
    '123': -1,
    '124': -1,
    '125': -1,
    '126': -1,
    '127': -1,
    '128': -1,
    '129': -1,
    '13': 5,
    '131': -1,
    '133': 125,
    '134': 126,
    '14': 6,
    '144': -1,
    '15': 7,
    '156': -1,
    '16': 8,
    '17': 9,
    '18': 10,
    '19': 11,
    '20': 12,
    '208': -1,
    '209': -1,
    '21': 13,
    '210': -1,
    '211': 115,
    '214': -1,
    '215': -1,
    '216': -1,
    '217': -1,
    '22': 14,
    '23': 15,
    '24': 16,
    '25': 17,
    '26': 18,
    '27': 19,
    '28': 20,
    '29': 21,
    '30': 22,
    '31': 23,
    '32': 24,
    '33': 25,
    '34': 26,
    '35': 27,
    '36': 28,
    '37': 29,
    '38': 30,
    '39': 31,
    '40': 32,
    '41': 33,
    '42': 34,
    '43': 35,
    '44': 36,
    '45': 37,
    '46': 38,
    '47': 39,
    '48': 40,
    '49': 41,
    '50': 42,
    '51': 43,
    '52': 44,
    '53': 45,
    '54': 46,
    '55': 47,
    '56': 48,
    '57': 49,
    '58': 50,
    '59': 51,
    '60': 52,
    '61': 53,
    '62': 54,
    '63': 55,
    '64': 56,
    '65': 57,
    '66': 58,
    '67': 59,
    '68': 60,
    '69': 61,
    '70': 62,
    '71': 63,
    '72': 64,
    '73': 65,
    '74': 66,
    '75': 67,
    '76': 68,
    '77': 69,
    '78': 70,
    '79': 71,
    '80': 72,
    '81': 73,
    '82': 74,
    '83': 75,
    '84': 76,
    '85': 77,
    '86': 78,
    '87': 79,
    '88': 80,
    '89': 81,
    '9': 1,
    '90': 82,
    '91': 83,
    '92': 84,
    '93': -1,
    '94': 86,
    '95': 87,
    '96': 88,
    '97': 94,
    '98': 95,
    '99': 96,
}
# ---- END GENERATED DATA ----

XKBSYM_TABLE_NONFREEBSD_ADD = {
    '0x1000': 'VoidSymbol',
    '0x13a4': 'VoidSymbol',
    '0xfe11': 'VoidSymbol',
    'Alt_L': 'Alt',
    'Alt_R': 'Alt',
    'BackSpace': 'Delete',
    'Begin': 'VoidSymbol',
    'Break': 'Break',
    'Cancel': 'VoidSymbol',
    'Caps_Lock': 'Caps_Lock',
    'Clear': 'VoidSymbol',
    'Codeinput': 'VoidSymbol',
    'Control_L': 'Control',
    'Control_R': 'Control',
    'Delete': 'Remove',
    'Down': 'Down',
    'Eisu_toggle': 'VoidSymbol',
    'End': 'End',
    'Escape': 'Escape',
    'Execute': 'VoidSymbol',
    'F1': 'F1',
    'F10': 'F10',
    'F11': 'F11',
    'F12': 'F12',
    'F13': 'F13',
    'F14': 'F14',
    'F15': 'F15',
    'F16': 'F16',
    'F17': 'F17',
    'F18': 'F18',
    'F19': 'F19',
    'F2': 'F2',
    'F20': 'F20',
    'F21': 'F21',
    'F22': 'F22',
    'F23': 'F23',
    'F24': 'F24',
    'F25': 'F25',
    'F26': 'F26',
    'F27': 'F27',
    'F28': 'F28',
    'F29': 'F29',
    'F3': 'F3',
    'F30': 'F30',
    'F31': 'F31',
    'F32': 'F32',
    'F33': 'F33',
    'F34': 'F34',
    'F35': 'F35',
    'F4': 'F4',
    'F5': 'F5',
    'F6': 'F6',
    'F7': 'F7',
    'F8': 'F8',
    'F9': 'F9',
    'Find': 'Find',
    'Hangul': 'VoidSymbol',
    'Hangul_Hanja': 'VoidSymbol',
    'Help': 'Help',
    'Henkan': 'VoidSymbol',
    'Hiragana': 'VoidSymbol',
    'Hiragana_Katakana': 'VoidSymbol',
    'Home': 'Home',
    'Hyper_L': 'Alt',
    'Hyper_R': 'Alt',
    'ISO_First_Group': 'ShiftL_Lock',
    'ISO_First_Group_Lock': 'ShiftL_Lock',
    'ISO_Group_Latch': 'ShiftL',
    'ISO_Group_Lock': 'ShiftL_Lock',
    'ISO_Group_Shift': 'ShiftL',
    'ISO_Last_Group': 'ShiftL_Lock',
    'ISO_Last_Group_Lock': 'ShiftL_Lock',
    'ISO_Left_Tab': 'Meta_Tab',
    'ISO_Level2_Latch': 'Shift',
    'ISO_Level3_Latch': 'AltGr',
    'ISO_Level3_Lock': 'AltGr_Lock',
    'ISO_Level3_Shift': 'AltGr',
    'ISO_Level5_Latch': 'AltGr',
    'ISO_Level5_Lock': 'AltGr_Lock',
    'ISO_Level5_Shift': 'AltGr',
    'ISO_Lock': 'Caps_Lock',
    'ISO_Next_Group': 'ShiftL_Lock',
    'ISO_Next_Group_Lock': 'ShiftL_Lock',
    'ISO_Prev_Group': 'ShiftL_Lock',
    'ISO_Prev_Group_Lock': 'ShiftL_Lock',
    'Insert': 'Insert',
    'KP_0': 'KP_0',
    'KP_1': 'KP_1',
    'KP_2': 'KP_2',
    'KP_3': 'KP_3',
    'KP_4': 'KP_4',
    'KP_5': 'KP_5',
    'KP_6': 'KP_6',
    'KP_7': 'KP_7',
    'KP_8': 'KP_8',
    'KP_9': 'KP_9',
    'KP_Add': 'KP_Add',
    'KP_Begin': 'VoidSymbol',
    'KP_Decimal': 'KP_Period',
    'KP_Delete': 'VoidSymbol',
    'KP_Divide': 'KP_Divide',
    'KP_Down': 'KP_2',
    'KP_End': 'KP_1',
    'KP_Enter': 'KP_Enter',
    'KP_Equal': 'equal',
    'KP_F1': 'F1',
    'KP_F2': 'F2',
    'KP_F3': 'F3',
    'KP_F4': 'F4',
    'KP_Home': 'KP_7',
    'KP_Insert': 'KP_0',
    'KP_Left': 'KP_4',
    'KP_Multiply': 'KP_Multiply',
    'KP_Next': 'KP_3',
    'KP_Page_Down': 'KP_3',
    'KP_Page_Up': 'KP_9',
    'KP_Prior': 'KP_9',
    'KP_Right': 'KP_6',
    'KP_Separator': 'KP_Comma',
    'KP_Seprator': 'KP_Comma',
    'KP_Space': 'space',
    'KP_Subtract': 'KP_Subtract',
    'KP_Tab': 'Tab',
    'KP_Up': 'KP_8',
    'Kanji': 'VoidSymbol',
    'Katakana': 'VoidSymbol',
    'L1': 'F11',
    'L10': 'F20',
    'L2': 'F12',
    'L3': 'F13',
    'L4': 'F14',
    'L5': 'F15',
    'L6': 'F16',
    'L7': 'F17',
    'L8': 'F18',
    'L9': 'F19',
    'Left': 'Left',
    'Linefeed': 'Linefeed',
    'Menu': 'VoidSymbol',
    'Meta_L': 'Alt',
    'Meta_R': 'Alt',
    'Mode_switch': 'ShiftL',
    'Muhenkan': 'VoidSymbol',
    'Multi_key': 'Compose',
    'MultipleCandidate': 'VoidSymbol',
    'Next': 'Next',
    'NoAction': 'NoSymbol',
    'NoSymbol': 'NoSymbol',
    'Nosymbol': 'NoSymbol',
    'Num_Lock': 'Num_Lock',
    'Page_Down': 'PageDown',
    'Page_Up': 'PageUp',
    'Pause': 'Pause',
    'Pointer_EnableKeys': 'VoidSymbol',
    'PreviousCandidate': 'VoidSymbol',
    'Print': 'Control_backslash',
    'Prior': 'Prior',
    'R1': 'F21',
    'R10': 'F30',
    'R11': 'F31',
    'R12': 'F32',
    'R13': 'F33',
    'R14': 'F34',
    'R15': 'F35',
    'R2': 'F22',
    'R3': 'F23',
    'R4': 'F24',
    'R5': 'F25',
    'R6': 'F26',
    'R7': 'F27',
    'R8': 'F28',
    'R9': 'F29',
    'Redo': 'VoidSymbol',
    'Return': 'Return',
    'Right': 'Right',
    'Scroll_Lock': 'Scroll_Lock',
    'Select': 'Select',
    'Shift_L': 'Shift',
    'Shift_Lock': 'Shift_Lock',
    'Shift_R': 'Shift',
    'SingleCandidate': 'VoidSymbol',
    'SunAgain': 'VoidSymbol',
    'SunAudioLowerVolume': 'VoidSymbol',
    'SunAudioMute': 'VoidSymbol',
    'SunAudioRaiseVolume': 'VoidSymbol',
    'SunCopy': 'VoidSymbol',
    'SunCut': 'VoidSymbol',
    'SunF36': 'VoidSymbol',
    'SunF37': 'VoidSymbol',
    'SunFA_Acute': 'dead_acute',
    'SunFA_Cedilla': 'dead_cedilla',
    'SunFA_Circum': 'dead_circumflex',
    'SunFA_Diaeresis': 'dead_diaeresis',
    'SunFA_Grave': 'dead_grave',
    'SunFA_Tilde': 'dead_tilde',
    'SunFind': 'VoidSymbol',
    'SunFront': 'VoidSymbol',
    'SunOpen': 'VoidSymbol',
    'SunPaste': 'VoidSymbol',
    'SunPowerSwitch': 'VoidSymbol',
    'SunPowerSwitchShift': 'VoidSymbol',
    'SunProps': 'VoidSymbol',
    'SunStop': 'VoidSymbol',
    'SunSys_Req': 'VoidSymbol',
    'SunUndo': 'VoidSymbol',
    'SunVideoDegauss': 'VoidSymbol',
    'SunVideoLowerBrightness': 'VoidSymbol',
    'SunVideoRaiseBrightness': 'VoidSymbol',
    'Super_L': 'Alt',
    'Super_R': 'Alt',
    'Sys_Req': 'Last_Console',
    'Tab': 'Tab',
    'Terminate_Server': 'VoidSymbol',
    'Undo': 'VoidSymbol',
    'Up': 'Up',
    'VoidSymbol': 'VoidSymbol',
    'XF86AudioForward': 'VoidSymbol',
    'XF86AudioLowerVolume': 'VoidSymbol',
    'XF86AudioMedia': 'VoidSymbol',
    'XF86AudioMute': 'VoidSymbol',
    'XF86AudioNext': 'VoidSymbol',
    'XF86AudioPause': 'VoidSymbol',
    'XF86AudioPlay': 'VoidSymbol',
    'XF86AudioPrev': 'VoidSymbol',
    'XF86AudioRaiseVolume': 'VoidSymbol',
    'XF86AudioRecord': 'VoidSymbol',
    'XF86AudioRewind': 'VoidSymbol',
    'XF86AudioStop': 'VoidSymbol',
    'XF86Back': 'VoidSymbol',
    'XF86Battery': 'VoidSymbol',
    'XF86Bluetooth': 'VoidSymbol',
    'XF86Calculator': 'VoidSymbol',
    'XF86Close': 'VoidSymbol',
    'XF86Copy': 'VoidSymbol',
    'XF86Cut': 'VoidSymbol',
    'XF86DOS': 'VoidSymbol',
    'XF86Display': 'VoidSymbol',
    'XF86Documents': 'VoidSymbol',
    'XF86Eject': 'VoidSymbol',
    'XF86Explorer': 'VoidSymbol',
    'XF86Favorites': 'VoidSymbol',
    'XF86Finance': 'VoidSymbol',
    'XF86Forward': 'VoidSymbol',
    'XF86HomePage': 'VoidSymbol',
    'XF86KbdBrightnessDown': 'VoidSymbol',
    'XF86KbdBrightnessUp': 'VoidSymbol',
    'XF86KbdLightOnOff': 'VoidSymbol',
    'XF86Launch1': 'VoidSymbol',
    'XF86Launch2': 'VoidSymbol',
    'XF86Launch3': 'VoidSymbol',
    'XF86Launch4': 'VoidSymbol',
    'XF86Mail': 'VoidSymbol',
    'XF86MailForward': 'VoidSymbol',
    'XF86MenuKB': 'VoidSymbol',
    'XF86MonBrightnessDown': 'VoidSymbol',
    'XF86MonBrightnessUp': 'VoidSymbol',
    'XF86MyComputer': 'VoidSymbol',
    'XF86New': 'VoidSymbol',
    'XF86Paste': 'VoidSymbol',
    'XF86Phone': 'VoidSymbol',
    'XF86PowerOff': 'VoidSymbol',
    'XF86Reload': 'VoidSymbol',
    'XF86Reply': 'VoidSymbol',
    'XF86RotateWindows': 'VoidSymbol',
    'XF86Save': 'VoidSymbol',
    'XF86ScreenSaver': 'VoidSymbol',
    'XF86ScrollDown': 'VoidSymbol',
    'XF86ScrollUp': 'VoidSymbol',
    'XF86Search': 'VoidSymbol',
    'XF86Send': 'VoidSymbol',
    'XF86Shop': 'VoidSymbol',
    'XF86Sleep': 'VoidSymbol',
    'XF86Suspend': 'VoidSymbol',
    'XF86Tools': 'VoidSymbol',
    'XF86TouchpadToggle': 'VoidSymbol',
    'XF86WLAN': 'VoidSymbol',
    'XF86WWW': 'VoidSymbol',
    'XF86WakeUp': 'VoidSymbol',
    'XF86WebCam': 'VoidSymbol',
    'XF86Xfer': 'VoidSymbol',
    'XF86_ClearGrab': 'VoidSymbol',
    'XF86_Next_VMode': 'VoidSymbol',
    'XF86_Prev_VMode': 'VoidSymbol',
    'XF86_Switch_VT_1': 'Console_1',
    'XF86_Switch_VT_10': 'Console_10',
    'XF86_Switch_VT_11': 'Console_11',
    'XF86_Switch_VT_12': 'Console_12',
    'XF86_Switch_VT_2': 'Console_2',
    'XF86_Switch_VT_3': 'Console_3',
    'XF86_Switch_VT_4': 'Console_4',
    'XF86_Switch_VT_5': 'Console_5',
    'XF86_Switch_VT_6': 'Console_6',
    'XF86_Switch_VT_7': 'Console_7',
    'XF86_Switch_VT_8': 'Console_8',
    'XF86_Switch_VT_9': 'Console_9',
    'XF86_Ungrab': 'VoidSymbol',
    'Zenkaku_Hankaku': 'VoidSymbol',
    'any': 'NoSymbol',
    'braille_blank': 'Brl_blank',
    'braille_dot_1': 'Brl_dot1',
    'braille_dot_10': 'Brl_dot10',
    'braille_dot_2': 'Brl_dot2',
    'braille_dot_3': 'Brl_dot3',
    'braille_dot_4': 'Brl_dot4',
    'braille_dot_5': 'Brl_dot5',
    'braille_dot_6': 'Brl_dot6',
    'braille_dot_7': 'Brl_dot7',
    'braille_dot_8': 'Brl_dot8',
    'braille_dot_9': 'Brl_dot9',
    'dead_V': 'dead_caron',
    'dead_abovedot': 'dead_abovedot',
    'dead_abovering': 'dead_abovering',
    'dead_acute': 'dead_acute',
    'dead_belowcomma': 'dead_belowcomma',
    'dead_belowdot': 'dead_belowdot',
    'dead_breve': 'dead_kbreve',
    'dead_caron': 'dead_kcaron',
    'dead_cedilla': 'dead_cedilla',
    'dead_circumflex': 'dead_circumflex',
    'dead_currency': 'dead_currency',
    'dead_dasia': 'VoidSymbol',
    'dead_diaeresis': 'dead_diaeresis',
    'dead_doubleacute': 'dead_kdoubleacute',
    'dead_doublegrave': 'dead_doublegrave',
    'dead_grave': 'dead_grave',
    'dead_hook': 'dead_hook',
    'dead_horn': 'dead_horn',
    'dead_invertedbreve': 'dead_invertedbreve',
    'dead_iota': 'dead_iota',
    'dead_macron': 'dead_macron',
    'dead_ogonek': 'dead_kogonek',
    'dead_psili': 'VoidSymbol',
    'dead_stroke': 'dead_stroke',
    'dead_tilde': 'dead_tilde',
    'guj_llla': 'VoidSymbol',
    'guj_nnna': 'VoidSymbol',
    'guj_rra': 'VoidSymbol',
    'gur_v_r': 'VoidSymbol',
    'gur_v_r_s': 'VoidSymbol',
    'gur_visarga': 'VoidSymbol',
    'leftcaret': 'VoidSymbol',
    'noSymbol': 'NoSymbol',
    'nosymbol': 'NoSymbol',
    'script_switch': 'VoidSymbol',
    'voidsymbol': 'VoidSymbol',
}

# ---- Unicode Alphabetic (Other_Alphabetic) correction ranges ----
_OTHER_ALPHABETIC_RANGES = [
    (837,837),(867,879),(1456,1469),(1471,1471),(1473,1474),(1476,1477),(1479,1479),
    (1552,1562),(1611,1623),(1625,1631),(1648,1648),(1750,1756),(1761,1764),(1767,1768),
    (1773,1773),(1809,1809),(1840,1855),(1958,1968),(2070,2071),(2075,2083),(2085,2087),
    (2089,2092),(2199,2199),(2260,2271),(2275,2281),(2288,2307),(2362,2363),(2366,2380),
    (2382,2383),(2389,2391),(2402,2403),(2433,2435),(2494,2500),(2503,2504),(2507,2508),
    (2519,2519),(2530,2531),(2561,2563),(2622,2626),(2631,2632),(2635,2636),(2641,2641),
    (2672,2673),(2677,2677),(2689,2691),(2750,2757),(2759,2761),(2763,2764),(2786,2787),
    (2810,2812),(2817,2819),(2878,2884),(2887,2888),(2891,2892),(2902,2903),(2914,2915),
    (2946,2946),(3006,3010),(3014,3016),(3018,3020),(3031,3031),(3072,3076),(3134,3140),
    (3142,3144),(3146,3148),(3157,3158),(3170,3171),(3201,3203),(3262,3268),(3270,3272),
    (3274,3276),(3285,3286),(3298,3299),(3315,3315),(3328,3331),(3390,3396),(3398,3400),
    (3402,3404),(3415,3415),(3426,3427),(3457,3459),(3535,3540),(3542,3542),(3544,3551),
    (3570,3571),(3633,3633),(3636,3642),(3661,3661),(3761,3761),(3764,3769),(3771,3772),
    (3789,3789),(3953,3971),(3981,3991),(3993,4028),(4139,4150),(4152,4152),(4155,4158),
    (4182,4185),(4190,4192),(4194,4196),(4199,4205),(4209,4212),(4226,4237),(4239,4239),
    (4250,4253),(5870,5872),(5906,5907),(5938,5939),(5970,5971),(6002,6003),(6070,6088),
    (6277,6278),(6313,6313),(6432,6443),(6448,6456),(6679,6683),(6741,6750),(6753,6772),
    (6847,6848),(6860,6862),(6912,6916),(6965,6979),(7040,7042),(7073,7081),(7084,7085),
    (7143,7153),(7204,7222),(7635,7668),(8544,8578),(8581,8584),(9398,9449),(11744,11775),
    (12295,12295),(12321,12329),(12344,12346),(42612,42619),(42654,42655),(42726,42735),
    (43010,43010),(43019,43019),(43043,43047),(43136,43137),(43188,43203),(43205,43205),
    (43263,43263),(43302,43306),(43335,43346),(43392,43395),(43444,43455),(43493,43493),
    (43561,43574),(43587,43587),(43596,43597),(43643,43645),(43696,43696),(43698,43700),
    (43703,43704),(43710,43710),(43755,43759),(43765,43765),(44003,44010),(64286,64286),
]

# is_alpha() replicates Perl's  pack("U",$uni) =~ /\p{IsAlpha}/  (Unicode
# Alphabetic property). Python's str.isalpha() matches for most codepoints but
# omits Other_Alphabetic (combining marks etc.); those extra ranges are added
# below. Both Perl 5.42 and this Python bundle Unicode 16.0.0, so the resulting
# set is byte-identical to upstream.

def _build_other_alpha():
    s = set()
    for a, b in _OTHER_ALPHABETIC_RANGES:
        for u in range(a, b + 1):
            s.add(u)
    return s


_OTHER_ALPHABETIC = None


def is_alpha(uni):
    global _OTHER_ALPHABETIC
    if 0 <= uni <= 0x10FFFF and chr(uni).isalpha():
        return True
    if _OTHER_ALPHABETIC is None:
        _OTHER_ALPHABETIC = _build_other_alpha()
    return uni in _OTHER_ALPHABETIC

# ==================== PORTED LOGIC ====================

import sys
import os
import re


def debug(*args):
    if DEBUG_FLAG:
        sys.stderr.write(" ".join(str(a) for a in args))


def warning(*args):
    sys.stderr.write("WARNING: " + " ".join(str(a) for a in args))


DEBUG_FLAG = 1


def die(msg):
    sys.stderr.write(msg)
    sys.exit(1)


# ---------- helpers to emulate perl string/list semantics ----------

class SparseList:
    """A list that auto-extends with None (emulates Perl sparse arrays)."""
    __slots__ = ("_d",)

    def __init__(self):
        self._d = []

    def __getitem__(self, i):
        if 0 <= i < len(self._d):
            return self._d[i]
        return None

    def __setitem__(self, i, v):
        if i < 0:
            raise IndexError(i)
        while len(self._d) <= i:
            self._d.append(None)
        self._d[i] = v

    def __len__(self):
        return len(self._d)

    def last_index(self):
        return len(self._d) - 1

    def clear(self):
        self._d = []


def perl_hex(s):
    """Emulate perl hex(): parse leading hex digits (optionally 0x), else 0."""
    if s is None:
        return 0
    m = re.match(r'\s*(?:0[xX])?([0-9a-fA-F]+)', s)
    if m:
        return int(m.group(1), 16)
    return 0


def _pl(lst, i):
    """Perl-style list index: out-of-range (or negative past start) -> None."""
    if 0 <= i < len(lst):
        return lst[i]
    return None


PROG = sys.argv[0]  # matches Perl's $0 (the invocation path)


# ==================== ARGUMENTS ====================

charmap = None
compose_charmap = None
acm = None
verbosity = 0

argv0 = sys.argv[0]
installdir = re.sub(r'/[^/]*$', '', argv0, flags=re.S)
if re.search(r'/bin$', installdir):
    installdir = re.sub(r'/bin$', '', installdir)
else:
    installdir += "/.."
if installdir == '' or not os.path.isdir(installdir + "/bin"):
    installdir = '/usr'

xdirs = ['/etc/console-setup/ckb',
         installdir + "/etc/console-setup/ckb",
         '/usr/local/share/X11/xkb',
         '/usr/share/X11/xkb',
         '/etc/X11/xkb']

keycodes = None
symbols = None

rules = None
model = None
layouts = []
variants = []
options = []
compact = 0
backspace = ''
freebsd = 0

ARGV = sys.argv[1:]


def perl_split_comma(s):
    # split(/,/, $s, -1) : keep trailing empties
    return s.split(',')


while ARGV:
    arg = ARGV.pop(0)
    if arg.startswith('-'):
        opt = arg[1:]
        if re.match(r'^charmap$', opt):
            if charmap:
                die("%s: No more than one -charmap option is allowed\n" % PROG)
            charmap = ARGV[0]
            ARGV.pop(0)
        elif re.match(r'^ccharmap$', opt):
            if compose_charmap:
                die("%s: No more than one -ccharmap option is allowed\n" % PROG)
            compose_charmap = ARGV[0]
            ARGV.pop(0)
        elif re.match(r'^v(erbose)?$', opt):
            if verbosity:
                die("%s: No more than one -verbose option is allowed\n" % PROG)
            if ARGV and re.match(r'^[0-9]|10$', ARGV[0]):
                verbosity = int(ARGV[0]) if ARGV[0].isdigit() else ARGV[0]
                ARGV.pop(0)
            else:
                verbosity = 5
        elif re.match(r'^I(.*)$', opt):
            m = re.match(r'^I(.*)$', opt)
            xdirs = [m.group(1)] + xdirs
        elif re.match(r'^keycodes$', opt):
            if keycodes:
                die("%s: No more than one -keycodes option is allowed\n" % PROG)
            keycodes = ARGV[0]
            ARGV.pop(0)
        elif re.match(r'^symbols$', opt):
            if symbols:
                die("%s: No more than one -symbols option is allowed\n" % PROG)
            symbols = ARGV[0]
            ARGV.pop(0)
        elif re.match(r'^rules$', opt):
            if rules:
                die("%s: No more than one -rules option is allowed\n" % PROG)
            rules = ARGV[0]
            ARGV.pop(0)
        elif re.match(r'^model$', opt):
            if model:
                die("%s: No more than one -model option is allowed\n" % PROG)
            model = ARGV[0]
            model = re.sub(r'[ \t\n\r\f\v]', '', model)
            ARGV.pop(0)
        elif re.match(r'^layout$', opt):
            if layouts:
                die("%s: No more than one -layout option is allowed\n" % PROG)
            a0 = re.sub(r'[ \t\n\r\f\v]', '', ARGV[0])
            layouts = perl_split_comma(a0)
            ARGV.pop(0)
        elif re.match(r'^variant$', opt):
            if variants:
                die("%s: No more than one -variant option is allowed\n" % PROG)
            a0 = re.sub(r'[ \t\n\r\f\v]', '', ARGV[0])
            variants = perl_split_comma(a0)
            ARGV.pop(0)
        elif re.match(r'^option$', opt):
            a0 = re.sub(r'[ \t\n\r\f\v]', '', ARGV[0])
            options = options + perl_split_comma(a0)
            ARGV.pop(0)
        elif re.match(r'^help$|^-help$|^\?$', opt):
            sys.stdout.write(
                "Usage: ckbcomp [args] [<layout> [<variant> [<option> ... ]]]\n"
                "Where legal args are:\n"
                "-?,-help            Print this message\n"
                "-charmap <name>     Specifies the encoding to use\n"
                "-ccharmap <name>    Specifies the encoding to use for compose sequences\n"
                "-I<dir>             Add <dir> to list of directories to be used\n"
                "-keycodes <name>    Specifies keycodes component name\n"
                "-symbols <name>     Specifies symbols component name\n"
                "-rules <name>       Name of rules file to use\n"
                "-model <name>       Specifies model used to choose component names\n"
                "-layout <name>      Specifies layout used to choose component names\n"
                "-variant <name>     Specifies layout variant used to choose component names\n"
                "-option <name>      Adds an option used to choose component names\n"
                "-v[erbose] [<lvl>]  Sets verbosity (1..10).  Higher values yield\n"
                "                    more messages\n"
                "-compact            Generate compact keymap\n"
                "-freebsd            Generate keymap for FreeBSD\n"
                "-backspace bs|del   Backspace is BS (^h) or DEL (^?)\n")
            sys.exit(0)
        elif re.match(r'^compact$', opt):
            compact = 1
        elif re.match(r'^freebsd$', opt):
            freebsd = 1
        elif re.match(r'^backspace$', opt):
            backspace = ARGV[0]
            if backspace != 'del' and backspace != 'bs':
                die("%s: Option -backspace accepts either del or bs\n" % PROG)
            ARGV.pop(0)
        else:
            die("%s: Unknown option -%s\n" % (PROG, opt))
    else:
        if not layouts:
            arg = re.sub(r'[ \t\n\r\f\v]', '', arg)
            layouts = perl_split_comma(arg)
            if not layouts or layouts == ['']:
                # split of '' with -1 gives [''] in perl; but perl code:
                # @layouts = split (/,/, $_, -1); @layouts=('us') if (! @layouts)
                # In perl split('',-1) on '' returns empty list, so ('us').
                pass
            if arg == '':
                layouts = ['us']
        elif not variants:
            arg = re.sub(r'[ \t\n\r\f\v]', '', arg)
            variants = perl_split_comma(arg)
            if arg == '':
                variants = ['']
        else:
            arg = re.sub(r'[ \t\n\r\f\v]', '', arg)
            options = options + perl_split_comma(arg)

if not rules:
    rules = 'base'
if not model:
    model = 'pc104'
if not backspace:
    backspace = 'bs' if freebsd else 'del'


# ==================== GLOBAL VARIABLES ====================

rules_variables = {}

arch = 'at'

acmtable = {}

KEYMAP = ['']  # use list wrapper so nested funcs can append

broken_caps = 0

keycodes_table = {}   # x keysym -> [x key codes...]
aliases = {}          # x keysym -> x keysym

symbols_table = {}    # x key code(str) -> [[level..],[..],...] per group
types_table = {}      # x key code(str) -> key type

augment_method = 1
override_method = 2
replace_method = 3
alternate_method = 4
ignore_method = 5

filename = ['']       # name of currently read file (list for closure mutation)
stream = ['']         # remaining unparsed contents
method = [override_method]
base_group = [0]

kernel_modifiers = KERNEL_MODIFIERS
modifier_combinations = MODIFIER_COMBINATIONS

forbidden = {}
for _i in range(0xf000, 0x10000):
    forbidden[_i] = 1

# ---- Build xkbsym_table ----
xkbsym_table = dict(XKBSYM_TABLE_BASE)
if freebsd:
    for _k, _v in XKBSYM_TABLE_FREEBSD_ADD.items():
        xkbsym_table[_k] = _v
    if backspace == 'del':
        xkbsym_table['BackSpace'] = 'del'
        xkbsym_table['Delete'] = 'fkey70'
        xkbsym_table['KP_Delete'] = 'fkey70'
else:
    for _k, _v in XKBSYM_TABLE_NONFREEBSD_ADD.items():
        xkbsym_table[_k] = _v

if compact:
    xkbsym_table['Mode_switch'] = 'AltGr'
    xkbsym_table['ISO_Group_Shift'] = 'AltGr'
    xkbsym_table['ISO_Group_Latch'] = 'AltGr'
    xkbsym_table['ISO_Group_Lock'] = 'AltGr_Lock'
    xkbsym_table['ISO_Next_Group'] = 'AltGr_Lock'
    xkbsym_table['ISO_Next_Group_Lock'] = 'AltGr_Lock'
    xkbsym_table['ISO_Prev_Group'] = 'AltGr_Lock'
    xkbsym_table['ISO_Prev_Group_Lock'] = 'AltGr_Lock'
    xkbsym_table['ISO_First_Group'] = 'AltGr_Lock'
    xkbsym_table['ISO_First_Group_Lock'] = 'AltGr_Lock'
    xkbsym_table['ISO_Last_Group'] = 'AltGr_Lock'
    xkbsym_table['ISO_Last_Group_Lock'] = 'AltGr_Lock'
if backspace == 'bs':
    xkbsym_table['BackSpace'] = 'BackSpace'
    xkbsym_table['Delete'] = 'Delete'

voidsymbol = 'nop' if freebsd else 'VoidSymbol'


# ---- control/meta symbols ----
controlsyms = SparseList()
metasyms = SparseList()
metacontrolsyms = SparseList()

if freebsd:
    controlsyms_hash = dict(CONTROLSYMS_HASH_FREEBSD)
else:
    controlsyms_hash = dict(CONTROLSYMS_HASH_LINUX)

for _special, _code in controlsyms_hash.items():
    controlsyms[_code] = _special

for _code in range(0, 256):
    if controlsyms[_code] is None:
        if 64 <= _code <= 127 and controlsyms[_code % 32] is not None:
            controlsyms[_code] = controlsyms[_code % 32]
        else:
            controlsyms[_code] = voidsymbol

if freebsd:
    controlsyms[0x08] = 'del'
    controlsyms[0x7f] = 'bs'
else:
    controlsyms[0x08] = 'Delete'
    controlsyms[0x7f] = 'BackSpace'

if freebsd:
    controlsyms[0x0d] = 'nl'
    controlsyms[0x20] = 'nul'
    controlsyms[0x3f] = 'del'
else:
    controlsyms[0x0d] = 'Control_m'
    controlsyms[0x20] = 'nul'
    controlsyms[0x2e] = 'Compose'
    controlsyms[0x3f] = 'Delete'

metasyms_hash = METASYMS_HASH

for _code in range(0, 256):
    _sym = chr(_code)
    if _sym in metasyms_hash:
        _sym = metasyms_hash[_sym]
    metasyms[_code] = "Meta_" + _sym

for _code in range(0, 256):
    _control = controlsyms[_code]
    if _control == 'Compose':
        metacontrolsyms[_code] = 'Compose'
    elif _control == 'Return':
        metacontrolsyms[_code] = 'Meta_Control_m'
    elif _control == 'NoSymbol':
        metacontrolsyms[_code] = 'NoSymbol'
    elif _control == 'VoidSymbol':
        metacontrolsyms[_code] = 'VoidSymbol'
    else:
        metacontrolsyms[_code] = 'Meta_' + _control


# ==================== GLOBAL FUNCTIONS ====================

def xfilename(f):
    base = re.sub(r'.*/(.+)', r'\1', f)
    for d in xdirs:
        if os.path.isfile(d + "/" + f):
            return d + "/" + f
        if os.path.isfile(d + "/" + base):
            return d + "/" + base
    die("%s: Can not find file \"%s\" in any known directory\n" % (PROG, f))


# ==================== READ THE RULES FILE ====================

def matches_pattern(string, pattern):
    if string == 'OPTIONS':
        for option in options:
            if option == '':
                continue
            if pattern == option:
                return 1
    else:
        if pattern == '*':
            return 1 if string != '' else 0
        m = re.match(r'^\$([a-zA-Z0-9_]+)$', pattern)
        if m:
            for member in rules_variables.get(m.group(1), []):
                if string == member:
                    return 1
            return 0
        if string == pattern:
            return 1
    return 0


if layouts:
    for i in range(len(layouts)):
        if i >= len(variants):
            variants.append('')
        elif variants[i] is None:
            variants[i] = ''
    rules_keycodes = None
    rules_symbols = None
    rules_path = xfilename("rules/" + rules)
    try:
        RULES = open(rules_path, 'r')
    except OSError as e:
        die("%s: %s: %s\n" % (PROG, rules_path, e.strerror))
    oldline = ''
    antecedents = []
    consequents = []
    match_found = 0
    for line in RULES:
        if re.match(r'^\s*//', line):
            continue
        if re.match(r'^\s*$', line):
            continue
        line = line.rstrip('\n')
        line = re.sub(r'^\s*', '', line)
        line = re.sub(r'\s+', ' ', line)
        if oldline:
            line = oldline + line
            oldline = ''
        m = re.search(r'\\$', line)
        if m:
            line = re.sub(r'\\$', ' ', line)
            oldline = line
            continue
        m = re.match(r'^! ?\$([a-zA-Z0-9_]+) ?= ?(.+)$', line)
        if m:
            rules_variables[m.group(1)] = m.group(2).split()
            continue
        m = re.match(r'^! ?(.+)= ?(.+)$', line)
        if m:
            antecedents = m.group(1).split()
            consequents = m.group(2).split()
            for i in range(len(antecedents)):
                a = antecedents[i]
                mm = re.search(r'layout\[([1-4])\]', a)
                mv = re.search(r'variant\[([1-4])\]', a)
                if a == 'model':
                    antecedents[i] = model
                elif a == 'layout' and len(layouts) == 1:
                    antecedents[i] = layouts[0]
                elif mm:
                    if len(layouts) > 1:
                        antecedents[i] = _pl(layouts, int(mm.group(1)) - 1)
                    else:
                        antecedents[i] = ''
                elif a == 'variant' and len(variants) == 1:
                    antecedents[i] = variants[0]
                elif mv:
                    if len(variants) > 1:
                        antecedents[i] = _pl(variants, int(mv.group(1)) - 1)
                    else:
                        antecedents[i] = ''
                elif a == 'option':
                    antecedents[i] = 'OPTIONS'
                elif a == 'layout' or a == 'variant':
                    antecedents[i] = ''
                else:
                    warning("Unknown name \"%s\" in the following line in \"rules/%s\":\n" % (a, rules))
                    warning("%s\n" % line)
                    antecedents[i] = ''
                if antecedents[i] is None:
                    antecedents[i] = ''
            match_found = 0
            continue
        m = re.match(r'^(.+)= ?(.+)$', line)
        if m:
            if match_found:
                continue
            antecedent_patterns = m.group(1).split()
            consequent_str = m.group(2)
            if len(antecedent_patterns) != len(antecedents):
                warning("Bad number of antecedents in the following line in \"rules/%s\":\n" % rules)
                warning("%s\n" % line)
                continue
            matches = 1
            for i in range(len(antecedents)):
                if not matches_pattern(antecedents[i], antecedent_patterns[i]):
                    matches = 0
                    break
            if matches:
                match_found = 1 if antecedents[0] != 'OPTIONS' else 0
                consequent_values = m.group(2).split()
                if len(consequent_values) != len(consequents):
                    warning("Bad number of consequents in the following line in \"rules/%s\":\n" % rules)
                    warning("%s\n" % line)
                for i in range(len(consequents)):
                    cv = consequent_values[i]
                    cv = cv.replace('%(', '(;%')
                    cv = cv.replace('%_', '_;%')
                    cv = re.sub(r'(%[lvm](\[[1-4]\])?)', r'\1;', cv)
                    cv = cv.replace('%m', model)
                    cv = cv.replace('%l[1]', layouts[0] if len(layouts) > 0 else '')
                    cv = cv.replace('%l[2]', layouts[1] if len(layouts) > 1 else '')
                    cv = cv.replace('%l[3]', layouts[2] if len(layouts) > 2 else '')
                    cv = cv.replace('%l[4]', layouts[3] if len(layouts) > 3 else '')
                    cv = cv.replace('%l', layouts[0] if len(layouts) > 0 else '')
                    cv = cv.replace('%v[1]', variants[0] if len(variants) > 0 else '')
                    cv = cv.replace('%v[2]', variants[1] if len(variants) > 1 else '')
                    cv = cv.replace('%v[3]', variants[2] if len(variants) > 2 else '')
                    cv = cv.replace('%v[4]', variants[3] if len(variants) > 3 else '')
                    cv = cv.replace('%v', variants[0] if len(variants) > 0 else '')
                    cv = cv.replace('(;;)', '')
                    cv = cv.replace('_;;', '')
                    cv = cv.replace(';', '')
                    consequent_values[i] = cv
                    if cv.startswith('+'):
                        if consequents[i] == 'keycodes':
                            rules_keycodes = (rules_keycodes or '') + cv
                        elif consequents[i] == 'symbols':
                            rules_symbols = (rules_symbols or '') + cv
                    else:
                        if consequents[i] == 'keycodes':
                            if not rules_keycodes:
                                rules_keycodes = cv
                        elif consequents[i] == 'symbols':
                            if not rules_symbols:
                                rules_symbols = cv
            continue
        warning("Syntax error in the following line in \"rules/%s\":\n" % rules)
        warning("%s\n" % line)
        die("")
    RULES.close()

    if verbosity != 0 and (verbosity == '' or int(verbosity) >= 1 if isinstance(verbosity, str) else verbosity >= 1):
        sys.stderr.write("Acording to the rules file:\n"
                         " keycodes = %s\n" % (rules_keycodes if rules_keycodes is not None else '')
                         + " symbols = %s\n" % (rules_symbols if rules_symbols is not None else ''))

    if not keycodes:
        keycodes = rules_keycodes
    if not symbols:
        symbols = rules_symbols

if not keycodes:
    die("%s: No keycodes, nor layout specified\n" % PROG)
if not symbols:
    die("%s: No symbols, nor layout specified\n" % PROG)


# ==================== COMPUTE ARCH ====================

if re.search(r'(^|\+|\|)ataritt(\([^\)]*\))?($|\+|\|)', keycodes):
    arch = 'ataritt'
elif re.search(r'(^|\+|\|)amiga(\([^\)]*\))?($|\+|\|)', keycodes):
    arch = 'amiga'
elif re.search(r'(^|\+|\|)sun(\(type[45][^\)]*\))?($|\+|\|)', keycodes):
    arch = 'sun'
elif re.search(r'(^|\+|\|)evdev(\([^\)]*\))?($|\+|\|)', keycodes):
    arch = 'evdev'


# ==================== READ ACM ====================

if charmap:
    for acmfile in (installdir + "/share/consoletrans/" + charmap,
                    installdir + "/share/consoletrans/" + charmap + ".gz",
                    installdir + "/share/consoletrans/" + charmap + ".acm",
                    installdir + "/share/consoletrans/" + charmap + ".acm.gz",
                    "/usr/share/consoletrans/" + charmap,
                    "/usr/share/consoletrans/" + charmap + ".gz",
                    "/usr/share/consoletrans/" + charmap + ".acm",
                    "/usr/share/consoletrans/" + charmap + ".acm.gz",
                    charmap):
        if os.path.isfile(acmfile):
            acm = acmfile
            break
    if not (acm and os.path.isfile(acm)):
        die("%s: no ACM for %s exists\n" % (PROG, charmap))
    if re.search(r'gz$', acm):
        import subprocess
        acmproc = subprocess.Popen(["zcat", acm], stdout=subprocess.PIPE)
        acmlines = acmproc.stdout.read().decode('utf-8').split('\n')
    else:
        with open(acm, 'r', encoding='utf-8') as fh:
            acmlines = fh.read().split('\n')
    for aline in acmlines:
        aline = re.sub(r'\#.*', '', aline)
        aline = aline.rstrip('\n')
        if not re.search(r'[^\s]', aline):
            continue
        m = re.match(r"^\s*0x([0-9a-fA-F]{1,2})\s+\'([^\']+)\'\s*$", aline)
        if m:
            uni = ord(m.group(2))
            c = int(m.group(1), 16)
            acmtable[uni] = c
        else:
            die("%s: Syntax error in ACM file: %s\n" % (PROG, aline))


# ==================== PARSING ====================

def syntax_error(what):
    die("%s: instead of \"%s\" in %s expected %s.\n"
        % (PROG, stream[0][0:50], filename[0], what))


def file_to_string(f):
    string = ''
    try:
        FILE = open(f, 'r')
    except OSError as e:
        die("%s: %s: %s\n" % (PROG, f, e.strerror))
    for line in FILE:
        line = line.rstrip('\n')
        line = re.sub(r'//.*', '', line)
        line = re.sub(r'\#.*', '', line)
        string = string + line + ' '
    FILE.close()

    normalized = ''
    final_letter = 0
    while string:
        m = re.match(r'^\s+', string)
        if m:
            string = string[m.end():]
            if final_letter and re.match(r'^[a-zA-Z0-9_]', string):
                normalized = normalized + ' '
                final_letter = 0
        m = re.match(r'^([^\"\s]+)', string)
        if m:
            normalized = normalized + m.group(1)
            final_letter = 1 if re.search(r'[a-zA-Z0-9_]$', m.group(1)) else 0
            string = string[m.end():]
            continue
        m = re.match(r'^(\"[^\"]*(\"|$))', string)
        if m:
            normalized = normalized + m.group(1)
            final_letter = 0
            string = string[m.end():]
            if m.group(2) != '"':
                die("%s: missing quote in %s...\n" % (PROG, m.group(1)[0:50]))
            continue
        if string:
            die("Internal error")
    stream[0] = normalized
    return normalized


def xkb_flags():
    default = 0
    while True:
        m = re.match(r'^(default|partial|hidden'
                     r'|alphanumeric_keys|modifier_keys'
                     r'|keypad_keys|function_keys'
                     r'|alternate_group)\s?(.*)', stream[0],
                     re.I | re.X | re.S)
        if not m:
            break
        stream[0] = m.group(2)
        if re.search(r'default', m.group(1), re.I):
            default = 1
    return default


def xkb_identifier():
    m = re.match(r'^([a-zA-Z0-1_]+) ?(.*)', stream[0], re.S)
    if m:
        stream[0] = m.group(2)
        return m.group(1)
    else:
        syntax_error("identifier")


def xkb_string():
    m = re.match(r'^\"([^\"]*)\"(.*)', stream[0], re.S)
    if m:
        stream[0] = m.group(2)
        return m.group(1)
    else:
        syntax_error("string")


def xkb_method():
    m = re.match(r'^alternate ?(.*)', stream[0], re.I | re.S)
    if m:
        stream[0] = m.group(1)
        return alternate_method
    m = re.match(r'^augment ?(.*)', stream[0], re.I | re.S)
    if m:
        stream[0] = m.group(1)
        return augment_method
    m = re.match(r'^replace ?(.*)', stream[0], re.I | re.S)
    if m:
        stream[0] = m.group(1)
        return replace_method
    m = re.match(r'^override ?(.*)', stream[0], re.I | re.S)
    if m:
        stream[0] = m.group(1)
        return override_method
    return method[0]


def xkb_include(file_type):
    m = re.match(r'^(include|replace|augment|override)\"([^\"]*)\";?(.*)',
                 stream[0], re.I | re.X | re.S)
    if m:
        stream[0] = m.group(3)
        method_name = m.group(1)
        include_request = m.group(2)
        if method[0] != ignore_method:
            oldmethod = method[0]
            if re.search(r'replace', method_name, re.I):
                method[0] = replace_method
            elif re.search(r'augment', method_name, re.I):
                method[0] = augment_method
            elif re.search(r'override', method_name, re.I):
                method[0] = override_method
            include_xkb_file(file_type, include_request)
            method[0] = oldmethod
        return 1
    else:
        return 0


def xkb_keycodes_definitions():
    oldmethod = method[0]
    while stream[0]:
        method[0] = oldmethod
        if xkb_include('keycodes'):
            continue
        method[0] = xkb_method()
        m = re.match(r'^(minimum|maximum|indicator|virtual\sindicator)[^;]*;(.*)',
                     stream[0], re.I | re.X | re.S)
        if m:
            stream[0] = m.group(2)
            continue
        if re.match(r'^<([^>]*)>=', stream[0]):
            m = re.match(r'^<([^>]+)>=([0-9]*);(.*)', stream[0], re.S)
            if not m:
                syntax_error("keycode definition")
            stream[0] = m.group(3)
            key = m.group(1)
            code = m.group(2)
            if (method[0] == replace_method
                    or method[0] == override_method
                    or (method[0] == augment_method
                        and key not in keycodes_table)):
                keycodes_table[key] = [code]
                aliases.pop(key, None)
            elif method[0] == alternate_method:
                keycodes_table.setdefault(key, []).append(code)
            continue
        if re.match(r'^alias', stream[0]):
            m = re.match(r'^alias<([^>]+)>=<([^>]+)>;(.*)', stream[0], re.S)
            if not m:
                syntax_error("alias definition")
            stream[0] = m.group(3)
            alias = m.group(1)
            key = m.group(2)
            if (method[0] == replace_method
                    or method[0] == override_method
                    or (method[0] == augment_method
                        and alias not in keycodes_table)):
                keycodes_table[alias] = []
                aliases[alias] = key
            continue
        break
    method[0] = oldmethod


def _st_get(code, group=None, level=None):
    """Access symbols_table[code][group][level] with perl-undef semantics."""
    entry = symbols_table.get(code)
    if group is None:
        return entry
    if entry is None:
        return None
    if group < len(entry):
        g = entry[group]
    else:
        g = None
    if level is None:
        return g
    if g is None:
        return None
    if level < len(g):
        return g[level]
    return None


def _st_set(code, group, level, value):
    if code not in symbols_table:
        symbols_table[code] = []
    entry = symbols_table[code]
    while len(entry) <= group:
        entry.append(None)
    if entry[group] is None:
        entry[group] = []
    g = entry[group]
    while len(g) <= level:
        g.append(None)
    g[level] = value


def _st_autoviv_code(code):
    """Perl-autovivify symbols_table[code] to an empty list if absent, and return
    it. Mirrors the side effect of Perl dereferencing $symbols_table{$code}[...]:
    the mere act of indexing into it creates the hash element as an arrayref. This
    is load-bearing for keys declared with an EMPTY symbol list (e.g. bqn's
    `key <AD06> { [ ] }`): Perl's `! defined $symbols_table{$code}[$group]` check
    autovivifies the key so it later flattens to an all-VoidSymbol keycode line."""
    if code not in symbols_table:
        symbols_table[code] = []
    return symbols_table[code]


def symbols_for_group(code, group, groupsymbols):
    # Perl: ($method == $override_method && (@_ || ! defined $symbols_table{$code}[$group])).
    # The `||` short-circuits, so the second operand is only evaluated when @_ is
    # empty. That second operand DEREFERENCES $symbols_table{$code}, which in Perl
    # autovivifies the hash element to an arrayref as a side effect -- load-bearing
    # for keys declared with an empty symbol list. Model it faithfully: only when
    # there are no symbols do we run _st_autoviv_code(code) (creating the key) and
    # then test whether its [group] slot is undefined.
    override_empty_check = False
    if method[0] == override_method and len(groupsymbols) == 0:
        entry = _st_autoviv_code(code)               # side-effect: create symbols_table[code]
        override_empty_check = (group >= len(entry)) or (entry[group] is None)
    if (method[0] == replace_method
            or (method[0] == override_method
                and (len(groupsymbols) > 0 or override_empty_check))
            or (method[0] == augment_method
                and symbols_table.get(code) is None)):
        level = 0
        for symbol in groupsymbols:
            if ('(' not in symbol and re.search(r'.', symbol, re.S)
                    and (symbol not in xkbsym_table
                         or xkbsym_table[symbol] != 'NoSymbol'
                         or _st_get(code, group, level) is None)):
                _st_set(code, group, level, symbol)
            level += 1


def xkb_key(default_key_type):
    if re.match(r'^key<', stream[0], re.I):
        m = re.match(r'^key<([^>]+)>\{([^\}]*?)\};(.*)', stream[0], re.I | re.S)
        if not m:
            syntax_error("key definition")
        stream[0] = m.group(3)
        key = m.group(1)
        lst = [m.group(2) + ","]
        if (verbosity_ge(4)) and key not in keycodes_table:
            warning("No scan code for <%s> is defined.\n" % key)
        for code in keycodes_table.get(key, []):
            if method[0] == replace_method:
                symbols_table[code] = []
            group = base_group[0]
            while re.search(r'[^ ]', lst[0]):
                m2 = re.match(r'^\[([^\]]*?)\],(.*)', lst[0], re.S)
                if m2:
                    lst[0] = m2.group(2)
                    symbols = m2.group(1).replace(',', ' ')
                    groupsymbols = symbols.split()
                    symbols_for_group(code, group, groupsymbols)
                    group += 1
                    continue
                m2 = re.match(r'^symbols=\[([^\]]*?)\],(.*)', lst[0], re.X | re.S)
                if m2:
                    lst[0] = m2.group(2)
                    symbols = m2.group(1).replace(',', ' ')
                    groupsymbols = symbols.split()
                    symbols_for_group(code, base_group[0], groupsymbols)
                    continue
                m2 = re.match(r'^symbols\[[Gg]roup([1-4])\]=\[([^\]]*?)\],(.*)',
                              lst[0], re.X | re.S)
                if m2:
                    grp = int(m2.group(1)) - 1 + base_group[0]
                    lst[0] = m2.group(3)
                    symbols = m2.group(2).replace(',', ' ')
                    groupsymbols = symbols.split()
                    symbols_for_group(code, grp, groupsymbols)
                    continue
                m2 = re.match(r'^type(?:\[[Gg]roup1\])?=?\"([^\"]+)\",(.*)',
                              lst[0], re.X | re.S)
                if m2:
                    lst[0] = m2.group(2)
                    if (method[0] == replace_method
                            or method[0] == override_method
                            or (method[0] == augment_method
                                and code not in types_table)):
                        types_table[code] = m2.group(1)
                    continue
                m2 = re.match(r'^[a-zA-Z0-9_]+(=[a-zA-Z0-9_<>]+)?,(.*)',
                              lst[0], re.X | re.S)
                if m2:
                    lst[0] = m2.group(2)
                    continue
                m2 = re.match(r'^[a-zA-Z0-9_]+=\"[^\"]+\",(.*)', lst[0], re.S)
                if m2:
                    lst[0] = m2.group(1)
                    continue
                m2 = re.match(r'^type\[[a-zA-Z0-9_]+\]=\"[^\"]+\",(.*)',
                              lst[0], re.X | re.S)
                if m2:
                    lst[0] = m2.group(1)
                    continue
                m2 = re.match(r'^actions\[[a-zA-Z0-9_]+\]=\[[^\]]*?\],(.*)',
                              lst[0], re.X | re.S)
                if m2:
                    lst[0] = m2.group(1)
                    continue
                die("%s: garbage in a key definition: \"%s\" in %s.\n"
                    % (PROG, lst[0], filename[0]))
            if (code not in types_table
                    or types_table[code] == 'DEFAULT'):
                types_table[code] = default_key_type
        return 1
    else:
        return 0


def verbosity_ge(n):
    if verbosity == 0:
        return False
    if isinstance(verbosity, str):
        try:
            return int(verbosity) >= n
        except ValueError:
            return False
    return verbosity >= n


def xkb_symbols_definitions():
    oldmethod = method[0]
    default_key_type = ['DEFAULT']
    while stream[0]:
        method[0] = oldmethod
        if xkb_include('symbols'):
            continue
        method[0] = xkb_method()
        if re.match(r'^name', stream[0], re.I):
            m = re.match(r'^name\[[a-zA-Z0-9_]+\]=\"[^\"]*\";(.*)', stream[0],
                         re.I | re.S)
            if not m:
                syntax_error("group name")
            stream[0] = m.group(1)
            continue
        m = re.match(r'^key\.type(?:\[[Gg]roup1\])?=\"([^\"]+)\";(.*)',
                     stream[0], re.S)
        if m:
            default_key_type[0] = m.group(1)
            stream[0] = m.group(2)
            continue
        m = re.match(r'^[a-zA-Z0-9_]+\.[a-zA-Z0-9_]+=.*?;(.*)', stream[0],
                     re.I | re.S)
        if m:
            stream[0] = m.group(1)
            continue
        m = re.match(r'^[a-zA-Z0-9_]+\.[a-zA-Z0-9_]+\[[a-zA-Z0-9_]+\]=.*?;(.*)',
                     stream[0], re.I | re.X | re.S)
        if m:
            stream[0] = m.group(1)
            continue
        if xkb_key(default_key_type[0]):
            continue
        if re.match(r'^(modifier_map|modmap|mod_map)', stream[0], re.I):
            m = re.match(r'^(modifier_map|modmap|mod_map)\s?[a-zA-Z0-9_]+\{[^\}]*\};(.*)',
                         stream[0], re.I | re.X | re.S)
            if not m:
                syntax_error("modifier_map")
            stream[0] = m.group(2)
            continue
        if re.match(r'^virtual_modifiers', stream[0], re.I):
            m = re.match(r'^virtual_modifiers\s?[a-zA-Z0-9_,]+;(.*)', stream[0],
                         re.I | re.X | re.S)
            if not m:
                syntax_error("virtual_modifiers")
            stream[0] = m.group(1)
            continue
        break
    method[0] = oldmethod


def xkb_definitions(file_type):
    if file_type == 'symbols':
        xkb_symbols_definitions()
    elif file_type == 'keycodes':
        xkb_keycodes_definitions()
    else:
        die("%s: Bad xkb file type %s\n" % (PROG, file_type))


def skip_to_brace():
    while stream[0]:
        m = re.match(r'^[^\}\{]*\{', stream[0], re.S)
        if not m:
            break
        stream[0] = stream[0][m.end():]
        skip_to_brace()
    m = re.match(r'^[^\}\{]*(\}|$)', stream[0], re.S)
    if m:
        stream[0] = stream[0][m.end():]


def xkb_block_list(file_type, block):
    first = 1
    ok = 0
    mystream = stream[0]
    while stream[0]:
        default = xkb_flags()
        if xkb_identifier() != "xkb_" + file_type:
            syntax_error("xkb_" + file_type)
        name = xkb_string()
        if stream[0][:1] == '{':
            stream[0] = stream[0][1:]
            structured = 1
        else:
            structured = 0
        if name == block or (first and not block):
            xkb_definitions(file_type)
            if structured:
                m = re.match(r'^\};.*', stream[0], re.S)
                if not m:
                    syntax_error("};")
                stream[0] = stream[0][m.end():]
            else:
                stream[0] = ''
            ok = 1
        else:
            if structured:
                skip_to_brace()
                if stream[0][:1] == ';':
                    stream[0] = stream[0][1:]
                else:
                    syntax_error(";")
            else:
                break
        first = 0
    if not ok:
        stream[0] = mystream
    return ok


def include_xkb_file(file_type, include_req):
    include_list = ['^' + include_req]
    oldmethod = method[0]
    oldbase_group = base_group[0]
    while include_list[0]:
        file = None
        block = None
        m = re.match(r'^(\^|\+|\|)([^\(\|\+]+)\(([^\)]+)\):([1234])(.*)',
                     include_list[0], re.X | re.S)
        if m:
            if m.group(1) == '+':
                method[0] = override_method
            elif m.group(1) == '|':
                method[0] = augment_method
            file = m.group(2)
            block = m.group(3)
            base_group[0] = int(m.group(4)) - 1 + base_group[0]
            include_list[0] = m.group(5)
        else:
            m = re.match(r'^(\^|\+|\|)([^\(\|\+]+)\(([^\)]+)\)(.*)',
                         include_list[0], re.X | re.S)
            if m:
                if m.group(1) == '+':
                    method[0] = override_method
                elif m.group(1) == '|':
                    method[0] = augment_method
                file = m.group(2)
                block = m.group(3)
                include_list[0] = m.group(4)
            else:
                m = re.match(r'^(\^|\+|\|)([^\(\|\+]+):([1234])(.*)',
                             include_list[0], re.S)
                if m:
                    if m.group(1) == '+':
                        method[0] = override_method
                    elif m.group(1) == '|':
                        method[0] = augment_method
                    file = m.group(2)
                    block = ''
                    base_group[0] = int(m.group(3)) - 1 + base_group[0]
                    include_list[0] = m.group(4)
                else:
                    m = re.match(r'^(\^|\+|\|)([^\(\|\+]+)(.*)',
                                 include_list[0], re.S)
                    if m:
                        if m.group(1) == '+':
                            method[0] = override_method
                        elif m.group(1) == '|':
                            method[0] = augment_method
                        file = m.group(2)
                        block = ''
                        include_list[0] = m.group(3)
                    else:
                        die("%s: bad include list %s.\n" % (PROG, include_list[0]))

        oldstream = stream[0]
        if re.match(r'^\.?/', file):
            stream[0] = file_to_string(file)
        else:
            stream[0] = file_to_string(xfilename(file_type + "/" + file))
        oldfilename = filename[0]
        filename[0] = file
        if not xkb_block_list(file_type, block):
            warning("Can not find \"%s\" in \"%s\".\n" % (block, file))
            xkb_block_list(file_type, '')

        if file == "gr":
            code = _kc0('AD02')
            if code is not None:
                symbol = _st_get(code, base_group[0], 1)
                if symbol == "Greek_SIGMA":
                    _st_set(code, base_group[0], 1, "dead_breve")

        stream[0] = oldstream
        filename[0] = oldfilename
        method[0] = oldmethod
        base_group[0] = oldbase_group


def _kc0(key):
    """keycodes_table{key}[0] with perl-undef semantics."""
    v = keycodes_table.get(key)
    if v is None or len(v) == 0:
        return None
    return v[0]


include_xkb_file('keycodes', keycodes)

for alias in list(aliases.keys()):
    if aliases[alias] not in keycodes_table:
        die("%s: undefined keyname %s in an keycode alias definition in %s.\n"
            % (PROG, aliases[alias], filename[0]))
    keycodes_table[alias] = list(keycodes_table[alias]) + list(keycodes_table[aliases[alias]])

include_xkb_file('symbols', symbols)

def _st_autoviv(code, group):
    """Perl-autovivification of symbols_table[code][group], mirroring what a Perl
    read of $symbols_table{code}[group][1] does to the CONTAINERS: it creates
    symbols_table[code] (list), extends it to include [group] (creating that slot
    as an empty list), and returns that group list. The final [1] element itself is
    NOT created (Perl only autovivifies intermediate containers, not the leaf
    scalar), so callers still read [1] non-destructively. This side effect is
    load-bearing: for layouts that define NO keys (e.g. `empty`, `bqn`) the mere
    `defined` checks below are what make keys 110/111 exist, so the AT loop later
    emits their all-VoidSymbol keycode lines -- exactly as the Perl original does."""
    if code not in symbols_table:
        symbols_table[code] = []
    entry = symbols_table[code]
    while len(entry) <= group:
        entry.append(None)
    if entry[group] is None:
        entry[group] = []
    return entry[group]


if arch == 'at' or arch == 'evdev':
    # Pause - 110, Break - 114, PrintScreen - 111, SysRq - 92.
    for group in range(0, 4):
        # no separate Break key on AT keyboards.  Break = Ctrl+Pause. Reading
        # [110][group][1] autovivifies symbols_table[110] + its [group] container
        # (see _st_autoviv) even when undefined, exactly like Perl.
        g110 = _st_autoviv('110', group)
        val110 = g110[1] if len(g110) > 1 else None
        if val110 is not None:
            symbols_table.setdefault('114', [])
            while len(symbols_table['114']) <= group:
                symbols_table['114'].append(None)
            symbols_table['114'][group] = [val110]
        # no separate SysRq key on AT keyboards.  SysRq = Alt+PrintScreen.
        g111 = _st_autoviv('111', group)
        val111 = g111[1] if len(g111) > 1 else None
        if val111 is not None:
            symbols_table.setdefault('92', [])
            while len(symbols_table['92']) <= group:
                symbols_table['92'].append(None)
            symbols_table['92'][group] = [val111]

for key in list(symbols_table.keys()):
    entry = symbols_table[key]
    for group in range(0, len(entry)):
        if entry[group] is None:
            entry[group] = []
        else:
            g = entry[group]
            for level in range(0, len(g)):
                if g[level] is None:
                    g[level] = 'NoSymbol'
    if key not in types_table:
        types_table[key] = 'DEFAULT'


# ==================== SYMBOL TRANSLATION ====================

def uni_to_legacy(uni):
    if acm:
        if uni <= 0x7f:
            if freebsd and 0x20 <= uni <= 0x7e:
                return "'%c'" % uni
            else:
                return "0x%02x" % uni
        elif uni in acmtable:
            if freebsd:
                return "%i" % acmtable[uni]
            else:
                return "0x%02x" % acmtable[uni]
        else:
            if verbosity_ge(8):
                warning("Unicode U+%04x does not exist in the legacy encoding\n" % uni)
            return voidsymbol
    else:
        return 'U+' + ("%04x" % uni)


def x_to_kernelsym(xkeysym):
    kernelkeysym = xkbsym_table.get(xkeysym)
    if kernelkeysym is not None:
        if not re.match(r'^[0-9][0-9a-fA-F]{3}$', kernelkeysym):
            return kernelkeysym
    else:
        m = re.match(r'^0x0*(100)?([0-9a-fA-F]{4})$', xkeysym)
        if m:
            kernelkeysym = m.group(2)
        else:
            m2 = re.match(r'^U([0-9a-fA-F]+)$', xkeysym)
            if m2:
                kernelkeysym = m2.group(1)
            else:
                kernelkeysym = None
    if kernelkeysym is not None:
        uni = perl_hex(kernelkeysym)
        if uni > 0xFFFF or uni in forbidden:
            if verbosity_ge(8):
                warning("Forbidden Unicode \"U+%s\"\n" % kernelkeysym)
            return voidsymbol
        else:
            if is_alpha(uni):
                legacy = uni_to_legacy(uni)
                if legacy != voidsymbol:
                    return '+' + legacy
                else:
                    return legacy
            elif uni <= 0x1f:
                return controlsyms[uni]
            else:
                return uni_to_legacy(uni)
    else:
        warning("Unknown X keysym \"%s\"\n" % xkeysym)
        return voidsymbol


def x_to_ascii(xkeysym):
    kernelkeysym = xkbsym_table.get(xkeysym)
    if kernelkeysym is not None:
        if kernelkeysym in controlsyms_hash:
            return controlsyms_hash[kernelkeysym]
        elif not re.match(r'^[0-9][0-9a-fA-F]{3}$', kernelkeysym):
            return None
    else:
        m = re.match(r'^0x0*(100)?([0-9a-fA-F]{4})$', xkeysym)
        if m:
            kernelkeysym = m.group(2)
        else:
            m2 = re.match(r'^U([0-9a-fA-F]+)$', xkeysym)
            if m2:
                kernelkeysym = m2.group(1)
            else:
                kernelkeysym = None
    if kernelkeysym is not None:
        uni = perl_hex(kernelkeysym)
        if 0x00 <= uni <= 0x7f:
            return uni
    return None


# ---- vectors ----
vector = SparseList()
numlockable = [0, 0, 0, 0]
quality = SparseList()


def approximate(coord, new_sym, new_quality):
    if ((quality[coord] is None or quality[coord] > new_quality)
            and new_sym != voidsymbol):
        vector[coord] = new_sym
        quality[coord] = new_quality


real_group_table = [[-1, -1, -1, -1],
                    [0, 0, 0, 0],
                    [0, 1, 1, 0],
                    [0, 1, 2, 0],
                    [0, 1, 3, 2]]


def flatten(key):
    global numlockable
    vector.clear()
    quality.clear()
    numlockable = [0, 0, 0, 0]
    entry = symbols_table.get(key, [])
    last_index_groups = len(entry) - 1
    for group in range(0, 4):
        real_group = real_group_table[1 + last_index_groups][group]
        last_level = None
        while real_group >= 0:
            g = entry[real_group] if real_group < len(entry) else None
            last_level = (len(g) - 1) if g is not None else -1
            if last_level < 0:
                real_group = real_group - 1
            else:
                break
        if real_group < 0:
            continue
        # last_level is set from the loop
        g = entry[real_group] if real_group < len(entry) else None
        last_level = (len(g) - 1) if g is not None else -1
        for level in range(0, 4):
            real_level = level
            kt = types_table[key]
            if kt == 'ONE_LEVEL':
                real_level = 0
            elif kt == 'TWO_LEVEL':
                real_level = real_level % 2
            elif kt == 'THREE_LEVEL':
                if real_level > 2:
                    real_level = 2
            if last_level == -1:
                continue
            elif last_level == 0:
                real_level = 0
            elif last_level == 1:
                real_level = real_level % 2
            elif last_level == 2 and real_level == 3:
                real_level = 2
            elif real_level > last_level:
                real_level = last_level
            coord = None
            if re.match(r'^(DEFAULT|ONE_LEVEL|TWO_LEVEL'
                        r'|THREE_LEVEL|ALPHABETIC'
                        r'|EIGHT_LEVEL|EIGHT_LEVEL_ALPHABETIC'
                        r'|EIGHT_LEVEL_SEMIALPHABETIC'
                        r'|FOUR_LEVEL|FOUR_LEVEL_ALPHABETIC'
                        r'|FOUR_LEVEL_SEMIALPHABETIC'
                        r'|SEPARATE_CAPS_AND_SHIFT_ALPHABETIC'
                        r'|KEYPAD|FOUR_LEVEL_X|FOUR_LEVEL_MIXED_KEYPAD'
                        r'|FOUR_LEVEL_KEYPAD|LOCAL_EIGHT_LEVEL'
                        r'|FOUR_LEVEL_PLUS_LOCK'
                        r')$', kt, re.X):
                coord = (group << 4) + level
            elif re.match(r'^(PC_BREAK|PC_CONTROL_LEVEL2'
                          r'|PC_LCONTROL_LEVEL2|PC_RCONTROL_LEVEL2)$', kt, re.X):
                if level == 0 or level == 2:
                    coord = (group << 4) + level
                else:
                    coord = (group << 4) + level + 3
            elif re.match(r'^(PC_SYSRQ|PC_ALT_LEVEL2'
                          r'|PC_LALT_LEVEL2|PC_RALT_LEVEL2)$', kt, re.X):
                if level == 0 or level == 2:
                    coord = (group << 4) + level
                else:
                    coord = (group << 4) + level + 7
            elif re.match(r'^SHIFT\+ALT$', kt):
                if level == 0 or level == 2:
                    coord = (group << 4) + level
                else:
                    coord = (group << 4) + level + 8
            elif re.match(r'^CTRL\+ALT$', kt):
                if level == 0 or level == 2:
                    coord = (group << 4) + level
                else:
                    coord = (group << 4) + level + 11
            elif re.match(r'^PC_FN_LEVEL2$', kt):
                coord = (group << 4) + (level << 1)
            else:
                warning("Unknown key type %s\n" % types_table[key])
                coord = (group << 4) + level
            xkeysym = _st_get(key, real_group, real_level)
            if re.match(r'^KP_', xkeysym):
                numlockable[group] = 1
            is_special = (not re.match(r'^U[0-9a-fA-F]+$', xkeysym)
                          and xkeysym in xkbsym_table
                          and not re.match(r'^[0-9][0-9a-fA-F]{3}$',
                                           xkbsym_table[xkeysym]))
            kernelkeysym = x_to_kernelsym(xkeysym)
            approximate(coord, kernelkeysym, 0)
            ascii = x_to_ascii(xkeysym)
            if ascii is not None:
                approximate((coord | 0x08), metasyms[ascii], 1)
                approximate((coord | 0x04), controlsyms[ascii], 1)
                approximate((coord | 0x0c), metacontrolsyms[ascii], 1)

    for x in range(0, 2):
        mask = 1 << x
        for coord in range(0, 64):
            if vector[coord] is None:
                continue
            # perl: $quality[$coord] + $mask << 2  == ($q + $mask) << 2
            approximate(coord ^ mask, vector[coord],
                        (quality[coord] + mask) << 2)
    for x in range(2, 4):
        mask = 1 << x
        for coord in range(0, 64):
            if vector[coord] is None:
                continue
            approximate(coord | mask, vector[coord],
                        (quality[coord] + mask) << 2)
    for coord in range(0, 17):
        if vector[coord] is None:
            continue
        for mask in (1 << 4, 2 << 4, 3 << 4):
            approximate(coord | mask, vector[coord],
                        (quality[coord] + 1) << 6)
    for coord in range(0, 64):
        if vector[coord] is None:
            vector[coord] = voidsymbol

    for coord in range(0, 64):
        if coord & 0x0c:
            continue
        mask = kernel_modifiers.get(vector[coord])
        if mask is None:
            continue
        for mod in (4, 8, 12):
            if (vector[coord + mod] == voidsymbol
                    and vector[(coord + mod) ^ mask] == voidsymbol):
                vector[coord + mod] = vector[coord]

    for coord in range(0, 64):
        mask = kernel_modifiers.get(vector[coord])
        if mask is not None:
            vector[coord ^ mask] = vector[coord]
            if compact and not freebsd:
                if (mask & 0x02) and (mask & 0x10):
                    vector[coord ^ mask ^ 0x02] = vector[coord]
                    vector[coord ^ mask ^ 0x10] = vector[coord]
                elif mask & 0x02:
                    vector[coord ^ mask ^ 0x10] = vector[coord]
                    vector[coord ^ mask ^ 0x10 ^ 0x02] = vector[coord]
                elif mask & 0x10:
                    vector[coord ^ mask ^ 0x02] = vector[coord]
                    vector[coord ^ mask ^ 0x02 ^ 0x10] = vector[coord]

    if freebsd or not compact:
        for coord in range(16, 64):
            if re.match(r'^(ShiftL|ShiftL_Lock|ashift|alock)$', vector[coord]):
                vector[coord] = voidsymbol
        for coord in range(0, 16):
            if vector[coord] == 'ShiftL_Lock':
                vector[coord + 16] = 'ShiftR_Lock'
                vector[coord + 32] = 'ShiftR_Lock'
                vector[coord + 48] = 'ShiftL_Lock'
            elif re.match(r'^(ShiftL|ashift|alock)$', vector[coord]):
                vector[coord + 16] = vector[coord]
                vector[coord + 32] = vector[coord]
                vector[coord + 48] = vector[coord]
    else:
        for coord in range(16, 64):
            if re.match(r'^(AltGr|AltGr_Lock)$', vector[coord]):
                vector[coord] = voidsymbol
        for coord in range(0, 16):
            if re.match(r'^(AltGr_Lock|AltGr)$', vector[coord]):
                vector[coord + 16] = vector[coord]
                vector[coord + 32] = vector[coord]
                vector[coord + 48] = vector[coord]

    for group in range(0, 4):
        kp = None
        for x in range(0, 16):
            coord = 16 * group + x
            if re.match(r'^KP_', vector[coord]):
                kp = vector[coord]
                break
        if (re.match(r'^(KEYPAD|FOUR_LEVEL_X'
                     r'|FOUR_LEVEL_MIXED_KEYPAD'
                     r'|FOUR_LEVEL_KEYPAD)$', types_table[key], re.X)
                and kp is None):
            kp = 'VoidSymbol'
            numlockable[group] = 1
        if kp and not freebsd:
            for x in range(0, 16):
                coord = 16 * group + x
                v = vector[coord]
                if re.match(r'^VoidSymbol$', v):
                    vector[coord] = kp
                elif re.search(xkbsym_table['plus'], v):
                    vector[coord] = 'KP_Add'
                elif re.search(xkbsym_table['minus'], v):
                    vector[coord] = 'KP_Subtract'
                elif re.search(xkbsym_table['asterisk'], v):
                    vector[coord] = 'KP_Multiply'
                elif re.search(xkbsym_table['slash'], v):
                    vector[coord] = 'KP_Divide'
                elif re.search(xkbsym_table['comma'], v):
                    vector[coord] = 'KP_Comma'
                elif re.search(xkbsym_table['period'], v):
                    vector[coord] = 'KP_Period'
                elif re.search(xkbsym_table['0'], v):
                    vector[coord] = 'KP_0'
                elif re.search(xkbsym_table['1'], v):
                    vector[coord] = 'KP_1'
                elif re.search(xkbsym_table['2'], v):
                    vector[coord] = 'KP_2'
                elif re.search(xkbsym_table['3'], v):
                    vector[coord] = 'KP_3'
                elif re.search(xkbsym_table['4'], v):
                    vector[coord] = 'KP_4'
                elif re.search(xkbsym_table['5'], v):
                    vector[coord] = 'KP_5'
                elif re.search(xkbsym_table['6'], v):
                    vector[coord] = 'KP_6'
                elif re.search(xkbsym_table['7'], v):
                    vector[coord] = 'KP_7'
                elif re.search(xkbsym_table['8'], v):
                    vector[coord] = 'KP_8'
                elif re.search(xkbsym_table['9'], v):
                    vector[coord] = 'KP_9'
                elif re.match(r'^(Return|Enter)$', v):
                    vector[coord] = 'KP_Enter'
                elif re.match(r'^Home$', v):
                    vector[coord] = 'KP_7'
                elif re.match(r'^Left$', v):
                    vector[coord] = 'KP_4'
                elif re.match(r'^Up$', v):
                    vector[coord] = 'KP_8'
                elif re.match(r'^Right$', v):
                    vector[coord] = 'KP_6'
                elif re.match(r'^Down$', v):
                    vector[coord] = 'KP_2'
                elif re.match(r'^Prior$', v):
                    vector[coord] = 'KP_9'
                elif re.match(r'^Next$', v):
                    vector[coord] = 'KP_3'
                elif re.match(r'^End$', v):
                    vector[coord] = 'KP_1'
                elif re.match(r'^Insert$', v):
                    vector[coord] = 'KP_0'

    for group in range(0, 4):
        coord = group << 4
        mainsym = vector[coord]
        m = re.match(r'^fkey([0-9]+)$', mainsym)
        if m:
            num = int(m.group(1))
            if 1 <= num <= 12:
                vector[coord + 1] = 'fkey' + str(num + 12)
                vector[coord + 4] = 'fkey' + str(num + 24)
                vector[coord + 5] = 'fkey' + str(num + 36)
                vector[coord + 2] = 'scr' + ("%02i" % num)
                x = "%02i" % (num + 10 if num <= 6 else num)
                vector[coord + 3] = 'scr' + x
                vector[coord + 6] = 'scr' + ("%02i" % num)
                vector[coord + 7] = 'scr' + x
            elif num == 52 or num == 56:
                sym = "'-'" if num == 52 else "'+'"
                for i in range(coord, coord + 16):
                    if vector[i] == mainsym and vector[i ^ 1] == mainsym:
                        vector[i | 1] = sym
            elif num == 60 and vector[coord + 1] == 'fkey60':
                vector[coord + 1] = 'paste'
        elif re.match(r'^esc$', mainsym):
            vector[coord + 6] = 'debug'
            vector[coord + 7] = 'debug'
        elif re.match(r'^saver$', mainsym):
            vector[coord] = 'slock'
            vector[coord + 1] = 'saver'
            vector[coord + 2] = 'susp'
            vector[coord + 3] = 'susp'
            vector[coord + 4] = 'slock'
            vector[coord + 5] = 'saver'
            vector[coord + 6] = 'susp'
            vector[coord + 7] = 'susp'
        elif freebsd and re.match(r"^\' \'$", mainsym):
            vector[coord + 6] = 'susp'
            vector[coord + 7] = 'susp'
        elif re.match(r'^ht$', mainsym):
            for i in range(coord, coord + 16):
                if vector[i] == 'ht' and vector[i ^ 1] == 'ht':
                    vector[i | 1] = 'btab'
        elif re.match(r'^nscr$', mainsym):
            for i in range(coord, coord + 16):
                if vector[i] == 'nscr' and vector[i ^ 1] == 'nscr':
                    vector[i | 1] = 'pscr'
            vector[coord + 4] = 'debug'
            vector[coord + 5] = 'debug'
        elif re.match(r'^F([0-9]+)$', mainsym):
            num = int(re.match(r'^F([0-9]+)$', mainsym).group(1))
            vector[coord + 1] = 'F' + str(num + 12)
            vector[coord + 2] = 'Console_' + str(num + 12)
            vector[coord + 3] = 'Console_' + str(num + 24)
            vector[coord + 4] = 'F' + str(num + 24)
            vector[coord + 5] = 'F' + str(num + 36)
            vector[coord + 6] = 'Console_' + str(num + 12)
            vector[coord + 7] = 'Console_' + str(num + 24)
            vector[coord + 8] = 'Console_' + str(num)
            vector[coord + 9] = 'Console_' + str(num + 12)
            vector[coord + 12] = 'Console_' + str(num)
            vector[coord + 13] = 'Console_' + str(num + 12)
        elif mainsym == 'Scroll_Lock' or mainsym == 'Help':
            vector[coord + 1] = 'Show_Memory'
            vector[coord + 2] = 'Show_Registers'
            vector[coord + 4] = 'Show_State'
            vector[coord + 8] = 'Show_Registers'
        elif re.match(r'^KP_([0-9])$', mainsym):
            num = re.match(r'^KP_([0-9])$', mainsym).group(1)
            vector[coord + 2] = 'Hex_' + num
            vector[coord + 9] = 'Hex_' + num
            vector[coord + 8] = 'Ascii_' + num
        elif mainsym == 'Num_Lock':
            vector[coord + 2] = 'Hex_A'
            vector[coord + 9] = 'Hex_A'
        elif mainsym == 'KP_Divide':
            vector[coord + 2] = 'Hex_B'
            vector[coord + 9] = 'Hex_B'
        elif mainsym == 'KP_Multiply':
            vector[coord + 2] = 'Hex_C'
            vector[coord + 9] = 'Hex_C'
        elif mainsym == 'KP_Subtract':
            vector[coord + 2] = 'Hex_D'
            vector[coord + 9] = 'Hex_D'
        elif mainsym == 'KP_Add':
            vector[coord + 2] = 'Hex_E'
            vector[coord + 9] = 'Hex_E'
        elif mainsym == 'KP_Enter':
            vector[coord + 2] = 'Hex_F'
            vector[coord + 9] = 'Hex_F'
        elif mainsym == 'Prior' or mainsym == 'PageUp':
            vector[coord + 1] = 'Scroll_Backward'
        elif mainsym == 'Next' or mainsym == 'PageDown':
            vector[coord + 1] = 'Scroll_Forward'
        elif mainsym == 'Left':
            vector[coord + 8] = 'Decr_Console'
        elif mainsym == 'Right':
            vector[coord + 8] = 'Incr_Console'
        elif mainsym == 'Up':
            vector[coord + 8] = 'KeyboardSignal'
    return vector


def print_vector(kernel_code):
    global broken_caps
    only_VoidSymbol = 1
    no_NoSymbol = 1
    for mask in range(0, 64):
        if vector[mask] != voidsymbol and vector[mask] != 'NoSymbol':
            only_VoidSymbol = 0
            break
    if only_VoidSymbol and compact:
        return
    for mask in range(0, 64):
        if vector[mask] == 'NoSymbol':
            no_NoSymbol = 0
            break
    if freebsd:
        capslockable = [0, 0, 0, 0]
        for group in range(0, 4):
            if re.match(r'^\+', vector[group * 16]):
                capslockable[group] = 1
                break
        for mask in range(0, 64):
            vector[mask] = re.sub(r'^\+', '', vector[mask])
            vector[mask] = re.sub(r'^NoSymbol$', 'nop', vector[mask])
        for group in range(0, 2):
            if group and not re.search(r':2', symbols):
                continue
            lockstate = (('B' if numlockable[group] else 'C')
                         if capslockable[group]
                         else ('N' if numlockable[group] else 'O'))
            KEYMAP[0] += "  %03i   " % (kernel_code + 128 * group)
            for mask in (0, 1, 4, 5, 2, 3, 6, 7):
                KEYMAP[0] += "%-6s " % vector[mask + 16 * group]
            KEYMAP[0] += " %s\n" % lockstate
    elif compact:
        if re.search(r':2', symbols):
            idx = [0, 1, 16, 17, 4, 20, 8, 24, 12, 28]
        else:
            idx = [0, 1, 2, 3, 4, 6, 8, 10, 12, 14]
        line = " ".join(vector[i] for i in idx)
        line = line.replace('NoSymbol', 'VoidSymbol')
        KEYMAP[0] += "keycode %s = %s\n" % (kernel_code, line)
    else:
        capsvector = [vector[i] for i in range(0, 64)]
        for mask in range(0, 64):
            m = re.match(r'^(\+?)U\+([0-9a-fA-F]+)$', capsvector[mask])
            if m:
                v = perl_hex(m.group(2))
                l = ord(chr(v).lower()) if len(chr(v).lower()) == 1 else _first_ord(chr(v).lower())
                u = ord(chr(v).upper()) if len(chr(v).upper()) == 1 else _first_ord(chr(v).upper())
                c = u if v == l else l
                capsvector[mask] = m.group(1) + "U+" + ("%04x" % c)
                if v != c and v > 0x7f:
                    broken_caps = 1
        if no_NoSymbol:
            vec_str = " ".join(vector[i] for i in range(0, 64))
            caps_str = " ".join(capsvector[i] for i in range(0, 64))
            KEYMAP[0] += "keycode %s = %s %s\n" % (kernel_code, vec_str, caps_str)
        else:
            for mask in range(0, 64):
                if vector[mask] != 'NoSymbol':
                    KEYMAP[0] += ("%s keycode %s = %s\n"
                                  % (modifier_combinations[mask], kernel_code, vector[mask]))
                    if re.search(r'plain', modifier_combinations[mask]):
                        KEYMAP[0] += ("ctrll keycode %s = %s\n"
                                      % (kernel_code, capsvector[mask]))
                    else:
                        KEYMAP[0] += ("ctrll %s keycode %s = %s\n"
                                      % (modifier_combinations[mask], kernel_code, capsvector[mask]))


def _first_ord(s):
    return ord(s[0])


at_scancodes = AT_SCANCODES
freebsd_scancodes = FREEBSD_SCANCODES


def sorted_symbols_keys():
    # perl: sort {$a <=> $b} keys %symbols_table  -> numeric sort
    return sorted(symbols_table.keys(), key=lambda k: int(k))


if freebsd:
    KEYMAP[0] += (
        "#                                                         alt\n"
        "# scan                       cntrl          alt    alt   cntrl lock\n"
        "# code  base   shift  cntrl  shift  alt    shift  cntrl  shift state\n"
        "# ------------------------------------------------------------------\n")
elif compact:
    KEYMAP[0] += "keymaps 0-4,6,8,10,12,14\n"
else:
    KEYMAP[0] += "keymaps 0-127\n"

if freebsd:
    for key in sorted_symbols_keys():
        kernel_code = freebsd_scancodes.get(key)
        if kernel_code is None or kernel_code < 0:
            continue
        flatten(key)
        if kernel_code == 83 or kernel_code == 103:
            for coord in (0 + 6, 0 + 7, 16 + 6, 16 + 7, 32 + 6, 32 + 7, 48 + 6, 48 + 7):
                vector[coord] = 'boot'
        print_vector(kernel_code)
elif arch == 'at' or arch == 'evdev':
    for key in sorted_symbols_keys():
        if arch == 'at':
            kernel_code = at_scancodes.get(key)
        else:
            kernel_code = int(key) - 8
        if kernel_code is None or kernel_code < 0:
            continue
        flatten(key)
        if kernel_code == 99:
            for coord in (0, 1, 16, 17, 32, 33, 48, 49):
                vector[coord] = 'VoidSymbol'
        elif kernel_code == 83 or kernel_code == 111:
            for coord in (0 + 6, 0 + 12, 0 + 14,
                          16 + 6, 16 + 12, 16 + 14,
                          32 + 6, 32 + 12, 32 + 14,
                          48 + 6, 48 + 12, 48 + 14):
                vector[coord] = 'Boot'
        print_vector(kernel_code)
elif arch == 'macintosh':
    for key in sorted_symbols_keys():
        kernel_code = int(key) - 8
        flatten(key)
        print_vector(kernel_code)
    KEYMAP[0] += ('\\\nkeycode 127 =\n        shift   control keycode 127 = Boot\n')
elif arch == 'ataritt':
    for key in sorted_symbols_keys():
        kernel_code = int(key) - 8
        if kernel_code == 97:
            vector.clear()
            base = ['F246', 'Break', 'F246', 'F246',
                    'F246', 'F246', 'F246', 'F246',
                    'Last_Console', 'F246', 'F246', 'F246',
                    'F246', 'F246', 'F246', 'F246'] * 4
            for i, v in enumerate(base):
                vector[i] = v
        else:
            flatten(key)
        if kernel_code == 83 or kernel_code == 113:
            for coord in (0 + 6, 0 + 12, 0 + 14,
                          16 + 6, 16 + 12, 16 + 14,
                          32 + 6, 32 + 12, 32 + 14,
                          48 + 6, 48 + 12, 48 + 14):
                vector[coord] = 'Boot'
        print_vector(kernel_code)
elif arch == 'amiga':
    for key in sorted_symbols_keys():
        kernel_code = int(key) - 8
        flatten(key)
        if kernel_code == 60:
            for coord in (0 + 6, 0 + 12, 0 + 14,
                          16 + 6, 16 + 12, 16 + 14,
                          32 + 6, 32 + 12, 32 + 14,
                          48 + 6, 48 + 12, 48 + 14):
                vector[coord] = 'Boot'
        print_vector(kernel_code)
elif arch == 'sun':
    for key in sorted_symbols_keys():
        kernel_code = int(key) - 7
        flatten(key)
        if kernel_code == 50:
            for coord in (0 + 6, 0 + 12, 0 + 14,
                          16 + 6, 16 + 12, 16 + 14,
                          32 + 6, 32 + 12, 32 + 14,
                          48 + 6, 48 + 12, 48 + 14):
                vector[coord] = 'Boot'
        print_vector(kernel_code)
else:
    die("%s: Unsupported keyboard type %s\n" % (PROG, arch))

if broken_caps:
    KEYMAP[0] = KEYMAP[0].replace('Caps_Lock', 'CtrlL_Lock')

sys.stdout.write(KEYMAP[0])

if not compose_charmap and charmap:
    compose_charmap = charmap

if freebsd:
    if compose_charmap:
        file1 = "/etc/console-setup/dkey.%s.inc" % compose_charmap
        file2 = installdir + "/etc/console-setup/dkey.%s.inc" % compose_charmap
        if os.path.isfile(file1):
            os.system("cat " + file1)
        elif os.path.isfile(file2):
            os.system("cat " + file2)
else:
    sys.stdout.write("strings as usual\n")
    if compose_charmap:
        file1 = "/etc/console-setup/compose.%s.inc" % compose_charmap
        file2 = installdir + "/etc/console-setup/compose.%s.inc" % compose_charmap
        if os.path.isfile(file1):
            os.system("cat " + file1)
        elif os.path.isfile(file2):
            os.system("cat " + file2)

file1 = "/etc/console-setup/remap.inc"
file2 = installdir + "/etc/console-setup/remap.inc"
if os.path.isfile(file1):
    os.system("cat " + file1)
elif os.path.isfile(file2):
    os.system("cat " + file2)

sys.exit(0)
