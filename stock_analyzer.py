import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
import requests
from typing import Dict, List, Optional, Tuple, Generator
from dotenv import load_dotenv
import json
from logger import get_logger

# 获取日志器
logger = get_logger()

class StockAnalyzer:
    def __init__(self, initial_cash=1000000, custom_api_url=None, custom_api_key=None, custom_api_model=None, custom_api_timeout=None):
        
        # 加载环境变量
        load_dotenv()
        
        # 设置 API 配置，优先使用自定义配置，否则使用环境变量
        self.API_URL = custom_api_url or os.getenv('API_URL')
        self.API_KEY = custom_api_key or os.getenv('API_KEY')
        self.API_MODEL = custom_api_model or os.getenv('API_MODEL', 'gpt-3.5-turbo')
        self.API_TIMEOUT = int(custom_api_timeout or os.getenv('API_TIMEOUT', 60))
        
        logger.debug(f"初始化StockAnalyzer: API_URL={self.API_URL}, API_MODEL={self.API_MODEL}, API_KEY={'已提供' if self.API_KEY else '未提供'}, API_TIMEOUT={self.API_TIMEOUT}")
        
        # 配置参数
        self.params = {
            'ma_periods': {'short': 5, 'medium': 20, 'long': 60},
            'rsi_period': 14,
            'bollinger_period': 20,
            'bollinger_std': 2,
            'volume_ma_period': 20,
            'atr_period': 14
        }

        
    def get_stock_data(self, stock_code, market_type='A', start_date=None, end_date=None, ):
        """获取股票数据"""
        import akshare as ak
        
        if start_date is None:
            start_date = (datetime.now() - timedelta(days=365)).strftime('%Y%m%d')
        if end_date is None:
            end_date = datetime.now().strftime('%Y%m%d')
            
        try:
            # 根据市场类型获取数据
            if market_type == 'A':
                df = ak.stock_zh_a_hist(
                    symbol=stock_code,
                    start_date=start_date,
                    end_date=end_date,
                    adjust="qfq"
                )
                # A股数据列名映射
            elif market_type == 'HK':
                df = ak.stock_hk_daily(
                    symbol=stock_code,
                    adjust="qfq"
                )
            elif market_type == 'US':
                df = ak.stock_us_hist(
                    symbol=stock_code,
                    start_date=start_date,
                    end_date=end_date,
                    adjust="qfq"
                )
            # elif market_type == 'CRYPTO':
            #     df = ak.crypto_js_spot(
            #         symbol=stock_code
            #     )
            else:
                raise ValueError(f"不支持的市场类型: {market_type}")
            
            # 重命名列名以匹配分析需求
            df = df.rename(columns={
                "日期": "date",
                "开盘": "open",
                "收盘": "close",
                "最高": "high",
                "最低": "low",
                "成交量": "volume"
            })
            
            # 确保日期格式正确
            df['date'] = pd.to_datetime(df['date'])
            
            # 数据类型转换
            numeric_columns = ['open', 'close', 'high', 'low', 'volume']
            df[numeric_columns] = df[numeric_columns].apply(pd.to_numeric, errors='coerce')
            
            # 删除空值
            df = df.dropna()
            
            return df.sort_values('date')
            
        except Exception as e:
            raise Exception(f"获取股票数据失败: {str(e)}")
            
    def calculate_ema(self, series, period):
        """计算指数移动平均线"""
        return series.ewm(span=period, adjust=False).mean()
        
    def calculate_rsi(self, series, period):
        """计算RSI指标"""
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))
        
    def calculate_macd(self, series):
        """计算MACD指标"""
        exp1 = series.ewm(span=12, adjust=False).mean()
        exp2 = series.ewm(span=26, adjust=False).mean()
        macd = exp1 - exp2
        signal = macd.ewm(span=9, adjust=False).mean()
        hist = macd - signal
        return macd, signal, hist
        
    def calculate_bollinger_bands(self, series, period, std_dev):
        """计算布林带"""
        middle = series.rolling(window=period).mean()
        std = series.rolling(window=period).std()
        upper = middle + (std * std_dev)
        lower = middle - (std * std_dev)
        return upper, middle, lower
        
    def calculate_atr(self, df, period):
        """计算ATR指标"""
        high = df['high']
        low = df['low']
        close = df['close'].shift(1)
        
        tr1 = high - low
        tr2 = abs(high - close)
        tr3 = abs(low - close)
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.rolling(window=period).mean()
        
    def calculate_indicators(self, df):
        """计算技术指标"""
        try:
            # 计算移动平均线
            df['MA5'] = self.calculate_ema(df['close'], self.params['ma_periods']['short'])
            df['MA20'] = self.calculate_ema(df['close'], self.params['ma_periods']['medium'])
            df['MA60'] = self.calculate_ema(df['close'], self.params['ma_periods']['long'])
            
            # 计算RSI
            df['RSI'] = self.calculate_rsi(df['close'], self.params['rsi_period'])
            
            # 计算MACD
            df['MACD'], df['Signal'], df['MACD_hist'] = self.calculate_macd(df['close'])
            
            # 计算布林带
            df['BB_upper'], df['BB_middle'], df['BB_lower'] = self.calculate_bollinger_bands(
                df['close'],
                self.params['bollinger_period'],
                self.params['bollinger_std']
            )
            
            # 成交量分析
            df['Volume_MA'] = df['volume'].rolling(window=self.params['volume_ma_period']).mean()
            df['Volume_Ratio'] = df['volume'] / df['Volume_MA']
            
            # 计算ATR和波动率
            df['ATR'] = self.calculate_atr(df, self.params['atr_period'])
            df['Volatility'] = df['ATR'] / df['close'] * 100
            
            # 动量指标
            df['ROC'] = df['close'].pct_change(periods=10) * 100
            
            return df
            
        except Exception as e:
            print(f"计算技术指标时出错: {str(e)}")
            raise
            
    def calculate_score(self, df):
        """计算股票评分"""
        try:
            score = 0
            latest = df.iloc[-1]
            
            # 趋势得分 (30分)
            if latest['MA5'] > latest['MA20']:
                score += 15
            if latest['MA20'] > latest['MA60']:
                score += 15
                
            # RSI得分 (20分)
            if 30 <= latest['RSI'] <= 70:
                score += 20
            elif latest['RSI'] < 30:  # 超卖
                score += 15
                
            # MACD得分 (20分)
            if latest['MACD'] > latest['Signal']:
                score += 20
                
            # 成交量得分 (30分)
            if latest['Volume_Ratio'] > 1.5:
                score += 30
            elif latest['Volume_Ratio'] > 1:
                score += 15
                
            return score
            
        except Exception as e:
            print(f"计算评分时出错: {str(e)}")
            raise
            
    def get_ai_analysis(self, df, stock_code, stream=False):
        """使用 OpenAI 进行 AI 分析"""
        try:
            logger.info(f"开始AI分析股票 {stock_code}, 流式模式: {stream}")
            recent_data = df.tail(14).to_dict('records')
            
            technical_summary = {
                'trend': 'upward' if df.iloc[-1]['MA5'] > df.iloc[-1]['MA20'] else 'downward',
                'volatility': f"{df.iloc[-1]['Volatility']:.2f}%",
                'volume_trend': 'increasing' if df.iloc[-1]['Volume_Ratio'] > 1 else 'decreasing',
                'rsi_level': df.iloc[-1]['RSI']
            }
            
            prompt = f"""
            分析股票 {stock_code}：

            技术指标概要：
            {technical_summary}
            
            近14日交易数据：
            {recent_data}
            
            请提供：
            1. 趋势分析（包含支撑位和压力位）
            2. 成交量分析及其含义
            3. 风险评估（包含波动率分析）
            4. 短期和中期目标价位
            5. 关键技术位分析
            6. 具体交易建议（包含止损位）
            
            请基于技术指标和市场动态进行分析，给出具体数据支持。
            """
            
            logger.debug(f"生成的AI分析提示词: {self._truncate_json_for_logging(prompt, 100)}...")
            
            # 检查API配置
            if not self.API_URL:
                error_msg = "API URL未配置，无法进行AI分析"
                logger.error(error_msg)
                return error_msg if not stream else (yield json.dumps({"error": error_msg}))
                
            if not self.API_KEY:
                error_msg = "API Key未配置，无法进行AI分析"
                logger.error(error_msg)
                return error_msg if not stream else (yield json.dumps({"error": error_msg}))
            
            # 标准化API URL  使用Cherry Studio相同逻辑处理
            if self.API_URL.endswith('/'):
                api_url = f"{self.API_URL}chat/completions"
            else:
                api_url = f"{self.API_URL}/v1/chat/completions"
            
            
            logger.debug(f"标准化后的API URL: {api_url}")
            
            # 构建请求头和请求体
            headers = {
                "Authorization": f"Bearer {self.API_KEY}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": self.API_MODEL,
                "messages": [{"role": "user", "content": prompt}]
            }
            
            # 流式处理设置
            if stream:
                logger.debug(f"配置流式参数，使用API URL: {api_url}")
                payload["stream"] = True  # 明确设置stream参数为True
                
                try:
                    logger.debug(f"发起流式API请求: {api_url}")
                    logger.debug(f"请求载荷: {self._truncate_json_for_logging(payload)}")
                    
                    response = requests.post(
                        api_url,
                        headers=headers,
                        json=payload,
                        timeout=self.API_TIMEOUT,  # 增加超时时间
                        stream=True
                    )
                    
                    logger.debug(f"API流式响应状态码: {response.status_code}")
                    
                    if response.status_code == 200:
                        logger.info(f"成功获取API流式响应，开始处理")
                        yield from self._process_ai_stream(response, stock_code)
                    else:
                        try:
                            error_response = response.json()
                            error_text = self._truncate_json_for_logging(error_response)
                        except:
                            error_text = response.text[:500] if response.text else "无响应内容"
                            
                        error_msg = f"API请求失败: 状态码 {response.status_code}, 响应: {error_text}"
                        logger.error(error_msg)
                        yield json.dumps({"stock_code": stock_code, "error": error_msg})
                        
                except Exception as e:
                    error_msg = f"流式API请求异常: {str(e)}"
                    logger.error(error_msg)
                    logger.exception(e)
                    yield json.dumps({"stock_code": stock_code, "error": error_msg})
            else:
                # 非流式处理
                logger.debug(f"发起非流式API请求: {api_url}")
                
                try:
                    response = requests.post(
                        api_url,
                        headers=headers,
                        json=payload,
                        timeout=self.API_TIMEOUT
                    )
                    
                    logger.debug(f"API非流式响应状态码: {response.status_code}")
                    
                    if response.status_code == 200:
                        api_response = response.json()
                        content = api_response['choices'][0]['message']['content']
                        logger.info(f"成功获取AI分析结果，长度: {len(content)}")
                        logger.debug(f"AI分析结果前100字符: {content[:100]}...")
                        return content
                    else:
                        try:
                            error_response = response.json()
                            error_text = self._truncate_json_for_logging(error_response)
                        except:
                            error_text = response.text[:500] if response.text else "无响应内容"
                            
                        error_msg = f"API请求失败: 状态码 {response.status_code}, 响应: {error_text}"
                        logger.error(error_msg)
                        return error_msg
                        
                except Exception as e:
                    error_msg = f"非流式API请求异常: {str(e)}"
                    logger.error(error_msg)
                    logger.exception(e)
                    return error_msg
            
        except Exception as e:
            error_msg = f"AI 分析过程中发生错误: {str(e)}"
            logger.error(error_msg)
            logger.exception(e)
            
            if stream:
                logger.debug("在流式模式下返回异常信息")
                error_json = json.dumps({"stock_code": stock_code, "error": error_msg})
                logger.info(f"流式异常输出: {error_json}")
                yield error_json
            else:
                return error_msg
    
    def _truncate_json_for_logging(self, json_obj, max_length=500):
        """截断JSON对象用于日志记录，避免日志过大
        
        Args:
            json_obj: 要截断的JSON对象
            max_length: 最大字符长度，默认500
            
        Returns:
            str: 截断后的JSON字符串
        """
        json_str = json.dumps(json_obj, ensure_ascii=False)
        if len(json_str) <= max_length:
            return json_str
        return json_str[:max_length] + f"... [截断，总长度: {len(json_str)}字符]"
    
    def _process_ai_stream(self, response, stock_code) -> Generator[str, None, None]:
        """处理AI流式响应"""
        logger.info(f"开始处理股票 {stock_code} 的AI流式响应")
        buffer = ""
        chunk_count = 0
        
        try:
            for line in response.iter_lines():
                if line:
                    line = line.decode('utf-8')
                    
                    # 跳过保持连接的空行
                    if line.strip() == '':
                        logger.debug("跳过空行")
                        continue
                        
                    # 数据行通常以"data: "开头
                    if line.startswith('data: '):
                        data_content = line[6:]  # 移除 "data: " 前缀
                        
                        # 检查是否为流的结束
                        if data_content.strip() == '[DONE]':
                            logger.debug("收到流结束标记 [DONE]")
                            break
                            
                        try:
                            json_data = json.loads(data_content)
                            
                            if 'choices' in json_data:
                                delta = json_data['choices'][0].get('delta', {})
                                content = delta.get('content', '')
                                
                                if content:
                                    chunk_count += 1
                                    buffer += content

                                    # 创建包含AI分析片段的JSON
                                    chunk_json = json.dumps({
                                        "stock_code": stock_code,
                                        "ai_analysis_chunk": content
                                    })
                                    yield chunk_json
                        except json.JSONDecodeError as e:
                            logger.error(f"JSON解析错误: {str(e)}, 行内容: {data_content}")
                            # 忽略无法解析的JSON
                            pass
                    else:
                        logger.warning(f"收到非'data:'开头的行: {line}")
            
            logger.info(f"AI流式处理完成，共收到 {chunk_count} 个内容片段，总长度: {len(buffer)}")
            
            # 如果buffer不为空，最后一次发送完整内容
            if buffer and not buffer.endswith('\n'):
                logger.debug("发送换行符")
                yield json.dumps({"stock_code": stock_code, "ai_analysis_chunk": "\n"})
        
        except Exception as e:
            error_msg = f"处理AI流式响应时出错: {str(e)}"
            logger.error(error_msg)
            logger.exception(e)
            yield json.dumps({"stock_code": stock_code, "error": error_msg})

    
    def get_recommendation(self, score):
        """根据得分给出建议"""
        logger.debug(f"根据评分 {score} 生成投资建议")
        if score >= 80:
            return '强烈推荐买入'
        elif score >= 60:
            return '建议买入'
        elif score >= 40:
            return '观望'
        elif score >= 20:
            return '建议卖出'
        else:
            return '强烈建议卖出'
    
    def analyze_stock(self, stock_code, market_type='A', stream=False):
        """分析单个股票"""
        try:
            logger.info(f"开始分析股票: {stock_code}, 市场: {market_type}, 流式模式: {stream}")
            
            # 获取股票数据
            logger.debug(f"获取股票 {stock_code} 数据")
            df = self.get_stock_data(stock_code, market_type)
            
            # 计算技术指标
            logger.debug(f"计算股票 {stock_code} 技术指标")
            df = self.calculate_indicators(df)
            
            # 评分系统
            logger.debug(f"计算股票 {stock_code} 评分")
            score = self.calculate_score(df)
            logger.info(f"股票 {stock_code} 评分结果: {score}")
            
            # 获取最新数据
            latest = df.iloc[-1]
            prev = df.iloc[-2]
            
            # 生成报告（保持原有格式）
            report = {
                'stock_code': stock_code,
                'analysis_date': datetime.now().strftime('%Y-%m-%d'),
                'score': score,
                'price': latest['close'],
                'price_change': (latest['close'] - prev['close']) / prev['close'] * 100,
                'ma_trend': 'UP' if latest['MA5'] > latest['MA20'] else 'DOWN',
                'rsi': latest['RSI'],
                'macd_signal': 'BUY' if latest['MACD'] > latest['Signal'] else 'SELL',
                'volume_status': 'HIGH' if latest['Volume_Ratio'] > 1.5 else 'NORMAL',
                'recommendation': self.get_recommendation(score)
            }
            logger.debug(f"生成股票 {stock_code} 基础报告: {self._truncate_json_for_logging(report, 100)}...")
            
            if stream:
                logger.info(f"以流式模式返回股票 {stock_code} 分析结果")
                # 先返回基本报告结构
                base_report = dict(report)
                base_report['ai_analysis'] = ''
                base_report_json = json.dumps(base_report)
                logger.debug(f"基础报告JSON: {self._truncate_json_for_logging(base_report_json, 100)}...")
                logger.info(f"发送基础报告: {base_report_json}")
                yield base_report_json
                
                # 然后流式返回AI分析部分
                logger.debug(f"开始获取股票 {stock_code} 的流式AI分析")
                ai_chunks_count = 0
                for ai_chunk in self.get_ai_analysis(df, stock_code, stream=True):
                    ai_chunks_count += 1
                    yield ai_chunk
                logger.info(f"股票 {stock_code} 流式AI分析完成，共发送 {ai_chunks_count} 个块")
            else:
                logger.info(f"以非流式模式返回股票 {stock_code} 分析结果")
                logger.debug(f"开始获取股票 {stock_code} 的AI分析")
                report['ai_analysis'] = self.get_ai_analysis(df, stock_code)
                logger.debug(f"AI分析结果长度: {len(report['ai_analysis'])}")
                return report
            
        except Exception as e:
            error_msg = f"分析股票 {stock_code} 时出错: {str(e)}"
            logger.error(error_msg)
            logger.exception(e)
            
            if stream:
                error_json = json.dumps({'stock_code': stock_code, 'error': error_msg})
                logger.info(f"流式错误输出: {error_json}")
                yield error_json
            else:
                raise
            
    def scan_market(self, stock_list, min_score=60, market_type='A', stream=False):
        """扫描市场，寻找符合条件的股票"""
        logger.info(f"开始扫描市场，股票数量: {len(stock_list)}, 最低分数: {min_score}, 市场: {market_type}, 流式模式: {stream}")
        
        if not stream:
            recommendations = []
            
            for stock_code in stock_list:
                try:
                    logger.debug(f"分析股票: {stock_code}")
                    report = self.analyze_stock(stock_code, market_type)
                    if report['score'] >= min_score:
                        logger.info(f"股票 {stock_code} 评分 {report['score']} >= {min_score}，添加到推荐列表")
                        recommendations.append(report)
                    else:
                        logger.debug(f"股票 {stock_code} 评分 {report['score']} < {min_score}，不添加到推荐列表")
                except Exception as e:
                    logger.error(f"分析股票 {stock_code} 时出错: {str(e)}")
                    logger.exception(e)
                    continue
                    
            # 按得分排序
            recommendations.sort(key=lambda x: x['score'], reverse=True)
            logger.info(f"扫描完成，找到 {len(recommendations)} 个推荐股票")
            return recommendations
        else:
            # 流式处理每个股票
            logger.info(f"开始流式扫描 {len(stock_list)} 只股票")
            stock_count = 0
            for stock_code in stock_list:
                stock_count += 1
                logger.debug(f"流式分析股票 {stock_code} ({stock_count}/{len(stock_list)})")
                try:
                    # 分析单只股票并获取流式结果
                    chunk_count = 0
                    for chunk in self.analyze_stock(stock_code, market_type, stream=True):
                        chunk_count += 1
                        yield chunk
                    logger.debug(f"股票 {stock_code} 流式分析完成，共 {chunk_count} 个块")
                except Exception as e:
                    error_msg = f"分析股票 {stock_code} 时出错: {str(e)}"
                    logger.error(error_msg)
                    logger.exception(e)
                    error_json = json.dumps({'stock_code': stock_code, 'error': error_msg})
                    logger.info(f"流式错误输出: {error_json}")
                    yield error_json
            logger.info(f"流式扫描完成，处理了 {stock_count} 只股票")
